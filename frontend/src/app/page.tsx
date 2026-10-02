"use client";
import {useCallback, useEffect, useRef, useState} from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {ArrowUp, ArrowUpRight, Check, ChevronDown, Copy, FileText, LoaderCircle, LogOut, Mail, MessageSquare, PanelLeftClose, PanelLeftOpen, Plus, RefreshCw, Search, ShieldCheck, Sparkles, Square, SquarePen, Users, X} from "lucide-react";
import {api, type ChatResult, type MailItem, type Session} from "@/lib/api";

type Message = {id: string; role: "user" | "assistant"; content: string; sources?: ChatResult["sources"]; error?: boolean};
type Conversation = {id: string; title: string; messages: Message[]};
const starters = [
  {icon: Users, title: "人物を探す", text: "社内で最年長の人を教えてください", caption: "名前や条件から、必要な人へ"},
  {icon: Search, title: "スキルを調べる", text: "Pythonの経験がある人を教えてください", caption: "経験と専門性を見つける"},
  {icon: FileText, title: "情報を整理する", text: "プロジェクト推進の経験がある人のスキルを整理してください", caption: "散らばる知識を、わかりやすく"},
];
function Mark() {
  return <svg viewBox="0 0 48 48" fill="none" aria-hidden="true"><path d="m24 3 6.3 14.7L45 24l-14.7 6.3L24 45l-6.3-14.7L3 24l14.7-6.3L24 3Z" stroke="currentColor" strokeWidth="1.3"/><path d="m24 14 10 10-10 10-10-10 10-10Z" fill="currentColor" opacity=".85"/></svg>;
}
function boundedHistory(messages: Message[]) {
  let remaining = 24000;
  const result: {role: "user" | "assistant"; content: string}[] = [];
  for (const m of messages.filter(m => !m.error).slice(-20).reverse()) {
    const content = m.content.slice(0, 8000);
    if (content.length > remaining) break;
    remaining -= content.length; result.unshift({role: m.role, content});
  }
  return result;
}
export default function ChatPage() {
  const [conversations, setConversations] = useState<Conversation[]>([{id: "initial", title: "新しいチャット", messages: []}]);
  const [activeId, setActiveId] = useState("initial");
  const [input, setInput] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [session, setSession] = useState<Session | null>(null);
  const [connectionError, setConnectionError] = useState("");
  const [pending, setPending] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const [mails, setMails] = useState<MailItem[] | null>(null);
  const [mailError, setMailError] = useState("");
  const [mailLoading, setMailLoading] = useState(false);
  const [accountBusy, setAccountBusy] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const textarea = useRef<HTMLTextAreaElement>(null);
  const scrollArea = useRef<HTMLDivElement>(null);
  const controller = useRef<AbortController | null>(null);
  const drawer = useRef<HTMLDialogElement>(null);
  const nearBottom = useRef(true);
  const active = conversations.find(c => c.id === activeId)!;
  const isEmpty = active.messages.length === 0;
  const needsLogin = session?.requires_login && !session.authenticated;

  const refreshSession = useCallback(async () => {
    try {setSession(await api<Session>("session/")); setConnectionError("");}
    catch {setSession(null); setConnectionError("サービスに接続できません。");}
  }, []);
  useEffect(() => {
    if (window.matchMedia("(max-width: 800px)").matches) setSidebarOpen(false);
    void refreshSession();
    const status = new URLSearchParams(window.location.search).get("connection");
    if (status) {
      setNotice(status === "success" ? "Microsoftに接続しました。" : "接続を完了できませんでした。もう一度お試しください。");
      window.history.replaceState({}, "", window.location.pathname);
    }
    return () => controller.current?.abort();
  }, [refreshSession]);
  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(""), 6000);
    return () => clearTimeout(timer);
  }, [notice]);
  useEffect(() => {
    if (textarea.current) {
      textarea.current.style.height = "auto";
      textarea.current.style.height = Math.min(textarea.current.scrollHeight, 176) + "px";
    }
  }, [input]);
  useEffect(() => {
    if (nearBottom.current && scrollArea.current) scrollArea.current.scrollTop = scrollArea.current.scrollHeight;
  }, [active.messages, pending]);
  useEffect(() => {
    nearBottom.current = true;
    if (scrollArea.current) scrollArea.current.scrollTop = scrollArea.current.scrollHeight;
  }, [activeId]);
  useEffect(() => {
    if (drawerOpen && !drawer.current?.open) drawer.current?.showModal();
    if (!drawerOpen && drawer.current?.open) drawer.current.close();
  }, [drawerOpen]);

  function append(id: string, message: Message) {
    setConversations(prev => prev.map(c => c.id === id ? {...c, messages: [...c.messages, message]} : c));
  }
  function newChat() {
    if (active.messages.length === 0) {textarea.current?.focus(); return;}
    const id = crypto.randomUUID();
    setConversations(prev => [{id, title: "新しいチャット", messages: []}, ...prev]);
    setActiveId(id); setInput("");
    if (window.innerWidth <= 800) setSidebarOpen(false);
    textarea.current?.focus();
  }
  async function send(value = input) {
    const query = value.trim();
    if (!query || controller.current || query.length > 4000 || !session) return;
    if (needsLogin) {setDrawerOpen(true); return;}
    const id = activeId, history = boundedHistory(active.messages);
    const request = new AbortController();
    controller.current = request; setPending(id); nearBottom.current = true;
    setConversations(prev => prev.map(c => c.id === id ? {...c,
      title: c.messages.length ? c.title : query,
      messages: [...c.messages, {id: crypto.randomUUID(), role: "user", content: query}],
    } : c));
    setInput("");
    let timedOut = false;
    const timer = setTimeout(() => {timedOut = true; request.abort();}, 180000);
    try {
      const data = await api<ChatResult>("chat/", {method: "POST", body: JSON.stringify({query, history}), signal: request.signal});
      append(id, {id: crypto.randomUUID(), role: "assistant", content: data.response, sources: data.sources});
    } catch (error) {
      append(id, {id: crypto.randomUUID(), role: "assistant", error: true,
        content: request.signal.aborted ? timedOut ? "応答に時間がかかっています。もう一度お試しください。" : "受信を停止しました。"
          : error instanceof Error ? error.message : "送信に失敗しました。"});
    } finally {clearTimeout(timer); controller.current = null; setPending(null); textarea.current?.focus();}
  }
  async function copy(message: Message) {
    try {await navigator.clipboard.writeText(message.content); setCopied(message.id); setTimeout(() => setCopied(null), 2000);}
    catch {setNotice("コピーできませんでした。テキストを選択してコピーしてください。");}
  }
  async function loadMails() {
    setMailLoading(true); setMailError("");
    try {setMails(await api<MailItem[]>("fetch-emails/"));}
    catch (error) {
      setMails(null); setMailError(error instanceof Error ? error.message : "メールを取得できませんでした。");
      await refreshSession();
    } finally {setMailLoading(false);}
  }
  function openOutlook() {
    setDrawerOpen(true);
    if (session?.authenticated && !mailLoading) void loadMails();
  }
  async function logout() {
    setAccountBusy(true);
    try {
      await api("logout/", {method: "POST"});
      controller.current?.abort(); setMails(null);
      setConversations([{id: "initial", title: "新しいチャット", messages: []}]);
      setActiveId("initial"); setInput(""); await refreshSession(); setNotice("接続を解除しました。");
    } catch {setNotice("接続を解除できませんでした。もう一度お試しください。");}
    finally {setAccountBusy(false);}
  }

  return <div className={"workspace " + (sidebarOpen ? "sidebar-visible" : "sidebar-hidden")}>
    {sidebarOpen && <button className="sidebar-scrim" aria-label="会話一覧を閉じる" onClick={() => setSidebarOpen(false)}/>}
    <aside className="sidebar" aria-label="会話一覧">
      <div className="brand-row"><a href="/" className="brand" aria-label="AETHER ホーム"><Mark/><span>AETHER</span></a>
        <button className="icon-button muted" onClick={() => setSidebarOpen(false)} aria-label="会話一覧を閉じる"><PanelLeftClose size={18}/></button></div>
      <button className="new-chat" onClick={newChat}><Plus size={18}/><span>新しいチャット</span><SquarePen size={16}/></button>
      <div className="sidebar-section-title">このタブの会話</div>
      <nav className="conversation-list">{conversations.map(c => <button key={c.id} className={"conversation-link " + (activeId === c.id ? "active" : "")}
        aria-current={activeId === c.id ? "page" : undefined}
        onClick={() => {setActiveId(c.id); setInput(""); if (window.innerWidth <= 800) setSidebarOpen(false);}}>
        <MessageSquare size={16}/><span>{c.title}</span>{pending === c.id && <LoaderCircle size={14} className="spin"/>}
      </button>)}</nav>
      <div className="sidebar-bottom">
        <button className="connection-card" onClick={openOutlook}><div className="connection-icon"><Mail size={19}/></div><span><strong>Outlook</strong><small>{session?.authenticated ? "接続済み・メールを確認" : "Microsoftと接続"}</small></span><ArrowUpRight size={16}/></button>
        <div className="sidebar-note"><ShieldCheck size={14}/>会話はこのタブ内だけに保持</div>
        <button className="profile-row" onClick={openOutlook}><span className="avatar">{session?.user?.displayName?.slice(0, 1) || "Y"}</span><span><strong>{session?.user?.displayName || "Your workspace"}</strong><small>{session?.authenticated ? "Microsoft account" : "Personal session"}</small></span><ChevronDown size={15}/></button>
      </div>
    </aside>
    <main className="main">
      <header className="topbar"><div className="topbar-left">
        {!sidebarOpen && <button className="icon-button" aria-label="会話一覧を開く" onClick={() => setSidebarOpen(true)}><PanelLeftOpen size={20}/></button>}
        <span className="topbar-title">AETHER <span>Workspace</span></span><span className="workspace-tag"><Sparkles size={12}/>社内ナレッジ</span>
      </div><div className="topbar-right"><span className={"status-pill " + (connectionError ? "offline" : "")}><i/>{connectionError ? "未接続" : !session ? "接続中" : session.mode === "demo" ? "デモモード" : "Azure モード"}</span><button className="icon-button" onClick={openOutlook} aria-label="Outlookを開く"><Mail size={19}/></button></div></header>
      <div className={"chat-scroll " + (isEmpty ? "empty-scroll" : "")} ref={scrollArea}
        onScroll={() => {const el = scrollArea.current; if (el) nearBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 100;}}>
        {isEmpty ? <section className="welcome" aria-labelledby="welcome-title">
          <div className="welcome-symbol"><Mark/></div><p className="eyebrow">A LITTLE CLARITY. A NEW POSSIBILITY.</p>
          <h1 id="welcome-title">知りたいことを、<br/><span>その先まで。</span></h1>
          <p className="welcome-description">社内の知識を、ひとつの会話へ。<br className="mobile-only"/>あなたの問いから始めましょう。</p>
          <div className="starter-grid">{starters.map(({icon: Icon, title, text, caption}) => <button key={title} className="starter-card" onClick={() => {setInput(text); textarea.current?.focus();}}>
            <div className="starter-top"><Icon size={20}/><ArrowUpRight size={15}/></div><strong>{title}</strong><span>{caption}</span>
          </button>)}</div>
          <div className="welcome-footnote"><span/>{session?.mode === "demo" ? "デモでは架空のサンプル回答を表示します" : "検索された情報をもとに回答します"}</div>
        </section> : <section className="messages" aria-label="チャットのメッセージ" aria-live="polite" aria-relevant="additions">
          {active.messages.map(message => <article key={message.id} className={"message " + message.role + (message.error ? " message-error" : "")}>
            {message.role === "assistant" && <div className="assistant-avatar"><Mark/></div>}
            <div className="message-main">
              {message.role === "assistant" && <div className="message-byline">AETHER <span>Assistant</span></div>}
              <div className="message-content">{message.role === "user" ? message.content :
                <ReactMarkdown remarkPlugins={[remarkGfm]} components={{a: ({children, href}) => <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>, img: () => <span>［画像は表示しません］</span>}}>{message.content}</ReactMarkdown>}</div>
              {!!message.sources?.length && <div className="sources"><span>参照情報</span>{message.sources.map((s, i) => <span className="source-chip" key={s.id + i}><FileText size={12}/>{s.name}</span>)}</div>}
              {message.role === "assistant" && !message.error && <button className="copy-button" onClick={() => void copy(message)} aria-label="回答をコピー">{copied === message.id ? <Check size={14}/> : <Copy size={14}/>} {copied === message.id ? "コピーしました" : "コピー"}</button>}
              {message.error && message.content !== "受信を停止しました。" && <button className="retry-button" disabled={!!pending} onClick={() => {
                const index = active.messages.findIndex(m => m.id === message.id);
                const question = active.messages.slice(0, index).reverse().find(m => m.role === "user");
                if (question) setInput(question.content); textarea.current?.focus();
              }}><RefreshCw size={13}/>質問を入力欄に戻す</button>}
            </div>
          </article>)}
          {pending === activeId && <article className="message assistant"><div className="assistant-avatar"><Mark/></div><div className="message-main"><div className="message-byline">AETHER <span>Assistant</span></div><div className="thinking"><span/><span/><span/><p>回答を準備しています</p></div></div></article>}
        </section>}
      </div>
      <div className="composer-region"><div className="composer-wrap">
        {connectionError && <div className="inline-error" role="alert"><span>{connectionError}</span><button onClick={() => void refreshSession()}><RefreshCw size={13}/>再接続</button></div>}
        {needsLogin && <div className="login-notice"><ShieldCheck size={15}/><span>社内情報を利用するにはMicrosoftに接続してください。</span><button onClick={openOutlook}>接続する</button></div>}
        <form className="composer" onSubmit={e => {e.preventDefault(); void send();}}>
          <label htmlFor="message-input" className="sr-only">メッセージ</label>
          <textarea id="message-input" ref={textarea} value={input} rows={1} maxLength={4000} onChange={e => setInput(e.target.value)}
            onKeyDown={e => {if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing && e.keyCode !== 229) {e.preventDefault(); void send();}}} placeholder="AETHER に聞いてみる…"/>
          <div className="composer-toolbar"><span className="composer-context"><Sparkles size={15}/>社内ナレッジ<span className="context-divider"/>{session?.mode === "demo" ? "Demo" : "Assistant"}</span>
            <div className="composer-actions">{input.length > 3600 && <span className="input-count">{input.length}/4000</span>}
              {pending ? <button type="button" className="send-button stop" aria-label="受信を停止" title="受信を停止" onClick={() => controller.current?.abort()}><Square size={15} fill="currentColor"/></button>
                : <button type="submit" className="send-button" aria-label="送信" disabled={!input.trim() || !session}><ArrowUp size={20} strokeWidth={2.2}/></button>}
            </div></div>
        </form>
        <div className="composer-caption"><span>回答には誤りが含まれる場合があります。重要な情報は原資料で確認してください。</span><span className="keyboard-hint">Shift + Enter で改行</span></div>
      </div></div>
    </main>
    <dialog ref={drawer} className="outlook-drawer" aria-labelledby="outlook-title" onCancel={() => setDrawerOpen(false)} onClose={() => setDrawerOpen(false)}
      onClick={e => {if (e.target === drawer.current && e.clientX < drawer.current.getBoundingClientRect().left) setDrawerOpen(false);}}>
      <div className="drawer-header"><div><span className="eyebrow">CONNECTED WORKSPACE</span><h2 id="outlook-title">Outlook</h2></div><button className="icon-button" aria-label="Outlookを閉じる" onClick={() => setDrawerOpen(false)}><X size={20}/></button></div>
      {session?.authenticated ? <>
        <div className="account-card"><ShieldCheck size={22}/><div><strong>{session.user?.displayName}</strong><span>{session.user?.userPrincipalName}</span></div></div>
        <div className="mail-toolbar"><h3>最近のメール</h3><button className="icon-button" disabled={mailLoading} onClick={() => void loadMails()} aria-label="メールを更新"><RefreshCw size={17} className={mailLoading ? "spin" : ""}/></button></div>
        <p className="drawer-description">最新10件の件名・送信者・受信日時を表示します。</p>
        {mailError && <p role="alert" className="mail-error">{mailError}</p>}
        {mailLoading && <div className="mail-loading"><LoaderCircle className="spin" size={20}/>メールを取得しています</div>}
        {!mailLoading && mails?.length === 0 && <p className="mail-empty">メールはありません。</p>}
        {!mailLoading && mails && <div className="mail-list">{mails.map((mail, i) => <article className="mail-item" key={mail.id || i}><div><strong>{mail.from?.emailAddress?.name || mail.from?.emailAddress?.address || "送信者不明"}</strong><time>{mail.receivedDateTime ? new Date(mail.receivedDateTime).toLocaleString("ja-JP", {month: "short", day: "numeric", hour: "2-digit", minute: "2-digit"}) : ""}</time></div><p>{mail.subject || "（件名なし）"}</p></article>)}</div>}
        <div className="drawer-bottom"><p>メール本文は取得せず、チャットの回答にも使用しません。</p><button className="secondary-button" onClick={() => void logout()} disabled={accountBusy}><LogOut size={16}/>接続を解除</button></div>
      </> : <div className="connect-empty"><div className="large-mail"><Mail size={30}/></div><h3>メールも、すぐそばに。</h3><p>Microsoftアカウントに接続すると、最近のメールをこのワークスペースで確認できます。</p>
        {session?.graph_configured ? <a className="primary-button" href={session.login_url}>Microsoftに接続<ArrowUpRight size={16}/></a>
          : <><button className="primary-button" disabled>Microsoft接続は未設定です</button><p className="setup-note">{session?.mode === "demo" ? "現在はデモモードです。実際のメールには接続していません。" : "管理者に接続設定をご確認ください。"}</p></>}
        <div className="connection-permissions"><ShieldCheck size={18}/><span>ユーザー情報とメールの読み取りのみ。<br/>メールの送信や削除は行いません。</span></div>
      </div>}
    </dialog>
    {notice && <div className="toast" role="status"><span>{notice}</span><button className="icon-button" onClick={() => setNotice("")} aria-label="通知を閉じる"><X size={16}/></button></div>}
  </div>;
}
