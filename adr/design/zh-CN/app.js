'use strict';

// 仅为中文交互原型。所有值均是合成演示；不读写文件、剪贴板或浏览器存储。
const PATHS = {
  password: '<rect x="4" y="10" width="16" height="11" rx="3"/><path d="M8 10V7a4 4 0 0 1 8 0v3M12 15v2"/>',
  verify: '<path d="M12 3 4 6v6c0 5 8 9 8 9s8-4 8-9V6l-8-3Z"/><path d="m8 12 3 3 5-6"/>',
  identity: '<rect x="3" y="5" width="18" height="14" rx="3"/><circle cx="8.5" cy="10" r="2"/><path d="M5 16c0-3 7-3 7 0M15 9h3M15 13h3"/>',
  bank: '<rect x="3" y="5" width="18" height="14" rx="3"/><path d="M3 10h18M7 15h3"/>',
  settings: '<path d="M4 7h16M4 17h16"/><circle cx="9" cy="7" r="3"/><circle cx="15" cy="17" r="3"/>',
  search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
  lock: '<rect x="5" y="10" width="14" height="11" rx="3"/><path d="M8 10V7a4 4 0 0 1 8 0v3M12 15v2"/>',
  theme: '<path d="M20 15.5A8.5 8.5 0 0 1 8.5 4 8.5 8.5 0 1 0 20 15.5Z"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  close: '<path d="m6 6 12 12M6 18 18 6"/>',
  arrow: '<path d="m9 5 7 7-7 7"/>',
  copy: '<rect x="8" y="8" width="12" height="13" rx="2"/><path d="M15 8V3H3v12h5"/>',
  eye: '<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>',
  key: '<circle cx="8" cy="9" r="5"/><path d="m12 13 8 8M16 17l3-3M18 19l3-3"/>',
  otp: '<circle cx="12" cy="13" r="8"/><path d="M9 2h6M12 9v4l3 2"/>',
  note: '<path d="M6 3h9l4 4v14H6V3Z"/><path d="M14 3v5h5M9 12h7M9 16h5"/>',
  star: '<path d="m12 3 2.8 5.8 6.4.9-4.6 4.5 1.1 6.3-5.7-3-5.7 3 1.1-6.3-4.6-4.5 6.4-.9L12 3Z"/>',
  sync: '<path d="M20 8a8 8 0 0 0-14-3L3 8M3 3v5h5M4 16a8 8 0 0 0 14 3l3-3M21 21v-5h-5"/>',
  terminal: '<rect x="3" y="4" width="18" height="16" rx="3"/><path d="m7 9 3 3-3 3M13 15h4"/>',
  download: '<path d="M12 3v12m-5-5 5 5 5-5M4 15v6h16v-6"/>',
  edit: '<path d="m4 16 12-12 4 4L8 20H4v-4ZM13 7l4 4"/>',
};
const icon = (name) => `<svg viewBox="0 0 24 24" aria-hidden="true">${PATHS[name] || PATHS.note}</svg>`;
const escapeHtml = (value) => String(value).replace(/[&<>"']/g, (character) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[character]));
const NAV = [
  {id:'password', label:'密码', description:'把常用账户与重要信息，留在自己手中。'},
  {id:'verify', label:'验证', description:'动态口令、通行密钥与 SSH 密钥，各归其位。'},
  {id:'identity', label:'证件', description:'妥善收好证件信息，及时留意有效期限。'},
  {id:'bank', label:'银行', description:'集中管理卡片与账户，敏感号码默认隐藏。'},
  {id:'settings', label:'设置', description:'密码库、设备保护和同步方式，由你决定。'},
];
const TYPE = {login:'登录信息',note:'安全备注',totp:'动态口令',passkey:'通行密钥',recovery:'恢复码',ssh:'SSH 密钥',identity:'证件',bank:'银行卡'};
const ENTRIES = [
  {id:'github',title:'GitHub',subtitle:'user@example.invalid',group:'开发工具',mark:'GH',tone:'',type:'login',category:'password',favorite:true,capabilities:['totp','passkey','recovery']},
  {id:'mail',title:'私人邮箱',subtitle:'mail@example.invalid',group:'日常生活',mark:'@',tone:'green',type:'login',category:'password',favorite:true,capabilities:[]},
  {id:'cloud',title:'云服务控制台',subtitle:'cloud@example.invalid',group:'开发工具',mark:'云',tone:'',type:'login',category:'password',favorite:false,capabilities:[]},
  {id:'note',title:'家庭网络备忘',subtitle:'路由器配置与设备说明',group:'日常生活',mark:'note',tone:'',type:'note',category:'password',favorite:false,capabilities:[]},
  {id:'ssh',title:'开发服务器',subtitle:'dev@server.example.invalid',group:'开发工具',mark:'terminal',tone:'green',type:'ssh',category:'verify',favorite:false,capabilities:['ssh']},
  {id:'passport',title:'护照',subtitle:'个人证件 · 号码已隐藏',group:'个人证件',mark:'identity',tone:'green',type:'identity',category:'identity',favorite:true,capabilities:[]},
  {id:'idcard',title:'身份证',subtitle:'个人证件 · 号码已隐藏',group:'个人证件',mark:'identity',tone:'',type:'identity',category:'identity',favorite:false,capabilities:[]},
  {id:'license',title:'驾驶证',subtitle:'出行证件 · 号码已隐藏',group:'出行',mark:'identity',tone:'',type:'identity',category:'identity',favorite:false,capabilities:[]},
  {id:'debit',title:'日常储蓄卡',subtitle:'演示银行 · 尾号 0000',group:'个人财务',mark:'bank',tone:'green',type:'bank',category:'bank',favorite:true,capabilities:[]},
  {id:'credit',title:'旅行信用卡',subtitle:'演示银行 · 尾号 1111',group:'个人财务',mark:'bank',tone:'',type:'bank',category:'bank',favorite:false,capabilities:[]},
];
const state = {page:'password',filter:'all',query:'',selection:'github:login',revealed:new Set(),theme:'dark',lastFocus:null};
const main = document.getElementById('main');
const modal = document.getElementById('modal');
const lockDialog = document.getElementById('lock-dialog');
let toastTimer;

function mark(entry) { return PATHS[entry.mark] ? icon(entry.mark) : escapeHtml(entry.mark); }
function rows() {
  if (state.query.trim()) {
    const query = state.query.trim().toLocaleLowerCase('zh-CN');
    return ENTRIES.filter((entry) => [entry.title,entry.subtitle,entry.group,TYPE[entry.type],...entry.capabilities.map((kind)=>TYPE[kind])].join(' ').toLocaleLowerCase('zh-CN').includes(query)).map((entry) => ({entry,kind:entry.type}));
  }
  let result = state.page === 'verify' ? ENTRIES.flatMap((entry)=>entry.capabilities.map((kind)=>({entry,kind}))) : ENTRIES.filter((entry)=>entry.category===state.page).map((entry)=>({entry,kind:entry.type}));
  if(state.filter==='favorite') result=result.filter(({entry})=>entry.favorite);
  else if(state.filter!=='all') result=result.filter(({kind})=>kind===state.filter);
  return result;
}
function showToast(message) { clearTimeout(toastTimer);const toast=document.getElementById('toast');toast.textContent=message;toast.hidden=false;toastTimer=setTimeout(()=>{toast.hidden=true;},4500); }
function hydrateIcons(root=document) { root.querySelectorAll('[data-icon]').forEach((element)=>{element.innerHTML=icon(element.dataset.icon);}); }
function renderNav() { document.getElementById('navigation').innerHTML=NAV.map((item)=>`<button class="nav-item" data-action="navigate" data-page="${item.id}" ${state.page===item.id?'aria-current="page"':''}>${icon(item.id)}<span>${item.label}</span></button>`).join(''); }
function header(page) { return `<div class="heading"><div><p class="eyebrow">个人密码库 · 演示</p><h1>${state.query?'搜索结果':page.label}</h1><p class="description">${state.query?'按标题、账户和分类搜索，不搜索秘密内容。':page.description}</p></div>${state.page!=='settings'?`<button class="primary" data-action="add">${icon('plus')}<span>新增</span></button>`:''}</div>`; }
function summaries() {
  const all=state.page==='verify'?ENTRIES.flatMap((entry)=>entry.capabilities):ENTRIES.filter((entry)=>entry.category===state.page);
  const first=state.page==='verify'?'验证方式':state.page==='identity'?'份证件':state.page==='bank'?'张卡片':'个条目';
  const second=state.page==='verify'?'4 类':'中文';
  return `<div class="summary-strip"><div class="summary-pill">${icon(state.page)}<span><strong>${all.length}</strong><small>${first}</small></span></div><div class="summary-pill">${icon(state.page==='verify'?'key':'verify')}<span><strong>${second}</strong><small>${state.page==='verify'?'验证凭据':'默认界面语言'}</small></span></div><div class="summary-pill">${icon('sync')}<span><strong>本地</strong><small>未配置同步</small></span></div></div>`;
}
function filters() {
  let values=state.page==='verify'?[['all','全部'],['totp','动态口令'],['passkey','通行密钥'],['recovery','恢复码'],['ssh','SSH 密钥']]:state.page==='password'?[['all','全部'],['favorite','收藏'],['login','登录信息'],['note','安全备注']]:[['all','全部'],['favorite','收藏']];
  if(state.query) values=[];
  return `<div class="toolbar"><div class="filters" aria-label="条目筛选">${values.map(([value,label])=>`<button class="filter ${state.filter===value?'active':''}" data-action="filter" data-filter="${value}" aria-pressed="${state.filter===value}">${label}</button>`).join('')}</div><span class="count-label">${rows().length} 个结果</span></div>`;
}
function rowMarkup({entry,kind}) {
  const key=`${entry.id}:${kind}`;
  return `<button class="entry-card ${state.selection===key?'selected':''}" data-action="select" data-selection="${key}" aria-label="查看${escapeHtml(entry.title)} · ${TYPE[kind]}"><span class="entry-icon ${entry.tone}">${mark(entry)}</span><span class="entry-text"><h3>${escapeHtml(entry.title)}</h3><p>${escapeHtml(entry.subtitle)}</p><span class="row-meta"><span class="tag ${kind==='totp'||kind==='passkey'?'purple':''}">${TYPE[kind]}</span>${kind==='login'&&entry.capabilities.length?'<span class="tag accent">含关联验证</span>':`<span class="tag">${escapeHtml(entry.group)}</span>`}</span></span><span class="entry-end ${entry.favorite?'favorite':''}">${icon(entry.favorite?'star':'arrow')}</span></button>`;
}
function field(entry,key,label,value,secret=false) {
  const revealed=state.revealed.has(`${entry.id}:${key}`);
  return `<div class="field"><div class="field-content"><span class="field-label">${label}</span><span class="field-value ${secret?'secret':''}">${secret&&!revealed?'•••• •••• ••••':escapeHtml(value)}</span></div>${secret?`<button class="icon-button" data-action="reveal" data-key="${entry.id}:${key}" aria-label="${revealed?'隐藏':'显示'}${label}" aria-pressed="${revealed}">${icon('eye')}</button>`:''}<button class="icon-button" data-action="copy" aria-label="复制${label}（演示）">${icon('copy')}</button></div>`;
}
function detailMarkup(entry,kind) {
  let content='';
  if(kind==='login') {
    content=`<p class="detail-section-label">登录信息</p>${field(entry,'user','用户名 / 邮箱',entry.subtitle)}${field(entry,'password','密码','DEMO-only-not-a-real-secret',true)}${field(entry,'url','网站',entry.id==='github'?'github.com':'example.invalid')}<div class="detail-actions"><button class="secondary" data-action="edit">${icon('edit')}编辑与生成</button><button class="secondary" data-action="info" data-topic="autofill">${icon('verify')}自动填充</button></div>`;
    if(entry.capabilities.length) content+=`<div class="related-heading"><span>关联验证</span><button class="text-button" data-action="open-verification">查看全部</button></div>${entry.capabilities.map((cap)=>`<div class="capability">${icon(cap==='totp'?'otp':cap==='passkey'?'key':'note')}<span>${TYPE[cap]}<small class="muted">与此账户关联，使用同一条目</small></span><span class="tag">演示</span></div>`).join('')}`;
  } else if(kind==='totp') content=`<p class="detail-section-label">动态口令（TOTP）</p>${field(entry,'user','关联账户',entry.subtitle)}<div class="otp-display"><strong>123 456</strong><small>固定演示码 · 不用于登录 · 正式版本按时间更新</small></div><button class="secondary full" data-action="copy">${icon('copy')}复制动态口令（演示）</button><div class="notice">动态口令与网站密码是不同凭据。种子应保存在受保护字段中，不能上传二维码解析服务。</div>`;
  else if(kind==='passkey') content=`<p class="detail-section-label">通行密钥（Passkey）</p>${field(entry,'rp','所属网站',entry.id==='github'?'github.com':'example.invalid')}${field(entry,'user','关联账户',entry.subtitle)}<div class="capability">${icon('key')}<span>软件通行密钥<small class="muted">库内存储 · 此处仅作界面演示</small></span><span class="tag">尚未接入</span></div><div class="notice">正式版本由系统或浏览器请求创建与认证。保存信息不等于已经支持登录；外部硬件密钥的私钥不能直接导入。</div><button class="text-button" data-action="info" data-topic="passkey">查看支持与实现边界</button>`;
  else if(kind==='recovery') content=`<p class="detail-section-label">网站恢复码</p>${field(entry,'recovery1','恢复码 1 · 演示','DEMO-0000',true)}${field(entry,'recovery2','恢复码 2 · 演示','DEMO-1111',true)}<div class="notice">恢复码用于恢复对应网站的账户访问，不用于找回密码库主密码。正式版本按条标记使用状态，默认不展示明文。</div>`;
  else if(kind==='ssh') content=`<p class="detail-section-label">SSH 密钥与代理</p>${field(entry,'algorithm','密钥类型','Ed25519（演示）')}${field(entry,'fingerprint','公钥指纹','未导入真实密钥')}${field(entry,'key','私钥','仅演示，未载入任何私钥',true)}<div class="capability">${icon('terminal')}<span>SSH 代理<small class="muted">每次签名确认 · 锁库撤销授权</small></span><span class="tag">尚未接入</span></div><div class="notice">桌面端规划实现 KeeAgent 数据兼容与 SSH Agent 协议。普通请求无法可靠说明远端主机；不会伪造“已授权目标主机”。</div><button class="text-button" data-action="info" data-topic="ssh">查看代理设置说明</button>`;
  else if(kind==='identity') content=`<p class="detail-section-label">证件信息</p>${field(entry,'name','持有人','演示用户',true)}${field(entry,'number','证件号码','DEMO-0000-0000',true)}${field(entry,'expiry','有效期至','2030年12月31日（示例）')}<div class="document-preview">${icon('identity')}<span>证件附件<small>尚未添加 · 此原型不接受文件</small></span></div><div class="notice">证件照片与号码仅用于个人保管，不等同于官方电子证件或在线身份认证。</div>`;
  else if(kind==='bank') content=`<div class="bank-preview"><p>演示银行 · ${entry.id==='debit'?'借记卡':'信用卡'}</p><strong>•••• •••• ${entry.id==='debit'?'0000':'1111'}</strong><small>演示卡片 · 非支付工具</small></div>${field(entry,'name','持卡人','演示用户',true)}${field(entry,'number','卡号','DEMO-CARD-NUMBER',true)}${field(entry,'expiry','有效期','12 / 30（示例）')}<div class="notice">CVV 与支付 PIN 不默认要求保存。卡片信息仅用于保管，不提供转账、支付或余额查询。</div>`;
  else content=`<p class="detail-section-label">安全备注</p>${field(entry,'note','内容','此处是家庭网络配置的合成演示说明。',true)}<div class="notice">真实内容使用 KDBX 受保护字段保存，列表不直接展开敏感备注。</div>`;
  return `<aside class="detail" aria-label="条目详情"><div class="detail-top"><span class="entry-icon ${entry.tone}">${mark(entry)}</span><div class="detail-heading"><h2>${escapeHtml(entry.title)}</h2><p>${escapeHtml(entry.group)} · ${TYPE[kind]}</p></div><button class="icon-button detail-close" data-action="close-detail" aria-label="关闭条目详情">${icon('close')}</button></div><div class="detail-body">${content}</div><div class="detail-footer"><span>演示条目 · 未接入真实密码库</span><button class="text-button" data-action="info" data-topic="history">历史记录</button></div></aside>`;
}
function settingsMarkup() {
  const group=(title,items)=>`<section class="settings-group"><h2>${title}</h2>${items.map(([key,name,desc,status,ico])=>`<button class="setting-row" data-action="${key==='theme'?'theme':'info'}" data-topic="${key}">${icon(ico)}<span class="setting-copy"><strong>${name}</strong><small>${desc}</small></span><span class="setting-state">${status}</span>${icon('arrow')}</button>`).join('')}</section>`;
  return `<div class="settings-layout"><div>${group('密码库与数据',[
    ['vault','管理密码库','打开、创建与切换 KDBX 文件','演示模式','password'],
    ['sync','同步与备份','先保存到本机，再确认远端同步','未配置','sync'],
    ['export','导入与导出','优先使用加密 KDBX 备份','尚未接入','download'],
  ])}${group('设备与验证',[
    ['biometric','解锁与隐私','主密码、设备认证与自动锁定','尚未接入','lock'],
    ['autofill','自动填充与通行密钥','按系统能力启用，不显示假开关','尚未接入','verify'],
    ['ssh','SSH 代理','密钥授权、签名确认与自动撤销','桌面功能','terminal'],
    ['audit','安全检查','检查重复、较弱与过期密码','尚未检查','key'],
  ])}${group('使用偏好',[
    ['theme','外观','深色 / 浅色，保持完整对比度',state.theme==='dark'?'深色':'浅色','theme'],
    ['language','语言','默认简体中文，保留协议和品牌名','简体中文','note'],
  ])}</div><aside class="settings-aside">${icon('verify')}<h2>本地优先，不必先有服务器</h2><p>密码库是你自己保管的加密文件。需要跨设备时，再选择 WebDAV 等同步服务。</p><div class="mini-divider"></div><h3>同步不是备份</h3><p>误删也可能被同步到其他设备。正式版本将保留加密备份，并提供冲突与恢复流程。</p><div class="mini-divider"></div><span class="tag">当前为交互原型</span><p>设备认证、代理与同步尚未接入。这里的状态不代表你的真实设备配置。</p></aside></div>`;
}
function render() {
  renderNav();
  const page=NAV.find((item)=>item.id===state.page);
  if(state.page==='settings'&&!state.query){main.innerHTML=header(page)+settingsMarkup();return;}
  const items=rows();
  if(!items.some(({entry,kind})=>`${entry.id}:${kind}`===state.selection)) state.selection=items[0]?`${items[0].entry.id}:${items[0].kind}`:null;
  const selected=items.find(({entry,kind})=>`${entry.id}:${kind}`===state.selection);
  const tip=state.page==='verify'?['分清凭据，不混淆验证','通行密钥不只是二次验证码；SSH 密钥也不是网站通行密钥。']:state.page==='identity'?['号码与附件，默认保持私密','正式应用将在授权后显示或导出，通知里不包含完整证件号。']:state.page==='bank'?['只保管，不支付','卡号默认遮罩。无需保存 CVV 或支付 PIN，也不连接银行账户。']:['更好的密码，从编辑时开始','生成器已移入新增与编辑流程；安全检查可在设置中打开。'];
  main.innerHTML=header(page)+(state.query?'':summaries())+filters()+`<div class="content-grid"><section class="entry-list" aria-label="条目列表">${items.length?items.map(rowMarkup).join(''):'<div class="empty"><h2>没有找到匹配的条目</h2><p>试试其他标题、账户或分类。</p></div>'}<div class="tip-card">${icon('verify')}<div><h3>${tip[0]}</h3><p>${tip[1]}</p></div></div></section>${selected?detailMarkup(selected.entry,selected.kind):''}</div>`;
}
const TOPICS={
  vault:['管理密码库','正式版本直接创建或打开 .kdbx 文件，以 KDBX 4.1 为新库目标。不同分类是同一密码库里的视图，不是五个独立库。','原型不打开文件，不收集主密码。'],
  sync:['同步与备份','先完成本地原子保存，再使用可选的 WebDAV 等密文文件同步。遇到并发修改保留双方版本，解决冲突后才确认同步。','没有服务器也能使用。未配置时不会显示“已同步”。'],
  export:['导入与导出','默认采用加密 KDBX 导出和备份；明文导出必须单独警示、授权。','原型不读取或导出文件。'],
  biometric:['解锁与隐私','主密码和可选密钥文件是基础。生物识别依赖本机系统保护，只解封经过授权的设备材料。','无法解锁时先核对文件、密钥文件和备份；没有万能主密码恢复。'],
  autofill:['自动填充','密码管理器需要系统凭据扩展或已配对的浏览器桥接。正式版本会核对网站或应用来源，再请求必要授权。','当前未连接系统服务，按钮不执行真实填充。'],
  passkey:['通行密钥的支持边界','正式版本需要完成密钥存储、注册与认证、系统 provider 和跨客户端兼容测试。Flutter 页面本身不等于 Passkey 提供者。','只显示已验证的平台能力，不把外部硬件私钥说成可同步。'],
  ssh:['SSH 代理','SSH 密钥放在“验证”，代理设置在这里。桌面端规划实现 Unix socket / Windows 适配与 KeeAgent 数据兼容。','默认按次或限时授权；锁库撤销自有代理能力。手机不承诺为其他任意 App 提供常驻代理。'],
  audit:['安全检查','正式版本默认只检查本地的重复、较弱和过期密码，逐条提供依据与处理入口。在线泄露查询需另外同意。','不会显示虚假安全分数，也无法替你一键修改所有网站密码。'],
  language:['中文优先','界面、提示和文档默认使用简体中文。协议名、品牌、URL、文件名及用户原始内容保持原样。','此规则已写入项目 AGENTS.md，后续 Flutter 使用统一 ARB 词条。'],
  history:['历史记录','正式版本在 KDBX 内保留条目历史，并支持回收站与版本恢复。不同客户端读写时必须保留这些数据。','当前展示的是合成条目，没有真实修改历史。'],
};
function openModal(title,content) { if(!modal.open)state.lastFocus=document.activeElement;document.getElementById('modal-content').innerHTML=`<h2 id="modal-title">${title}</h2>${content}`;if(!modal.open)modal.showModal(); }
function info(topic) { const data=TOPICS[topic]||TOPICS.vault;openModal(data[0],`<p>${data[1]}</p><div class="notice">${data[2]}</div><div class="modal-actions"><button class="primary" data-action="close-modal">知道了</button></div>`); }
function addOrEdit(edit=false) {
  const page=NAV.find((item)=>item.id===state.page);
  openModal(edit?'编辑密码 · 流程预览':`新增${page.id==='verify'?'验证方式':page.label} · 流程预览`,`<p>原型只展示操作布局，不接收或保存真实数据。</p><label class="form-label">条目名称<input value="演示条目" disabled></label><label class="form-label">分类<input value="${page.label}" disabled></label>${state.page==='password'?'<label class="form-label">密码<input type="password" value="demonstration-only" disabled></label><button class="secondary" data-action="generator">'+icon('key')+'打开密码生成器</button>':'<div class="notice">正式版本将根据分类提供对应字段；新增与保存遵循统一授权和原子写入流程。</div>'}<div class="modal-actions"><button class="primary" data-action="save-explanation">查看保存流程</button><button class="quiet" data-action="close-modal">取消</button></div>`);
}
function lock() { if(modal.open)modal.close();state.revealed.clear();document.body.classList.remove('detail-open');render();document.getElementById('toast').hidden=true;if(!lockDialog.open)lockDialog.showModal(); }
document.addEventListener('click',(event)=>{
  const element=event.target.closest('[data-action]');if(!element)return;
  const action=element.dataset.action;
  if(action==='navigate'){state.page=element.dataset.page;state.query='';state.filter='all';state.selection=null;state.revealed.clear();document.getElementById('search').value='';document.body.classList.remove('detail-open');render();window.scrollTo(0,0);}
  else if(action==='filter'){state.filter=element.dataset.filter;state.selection=null;state.revealed.clear();render();}
  else if(action==='select'){state.selection=element.dataset.selection;state.revealed.clear();document.body.classList.add('detail-open');render();}
  else if(action==='close-detail'){document.body.classList.remove('detail-open');state.revealed.clear();render();}
  else if(action==='theme'){state.theme=state.theme==='dark'?'light':'dark';document.documentElement.dataset.theme=state.theme;render();}
  else if(action==='reveal'){const key=element.dataset.key;state.revealed.has(key)?state.revealed.delete(key):state.revealed.add(key);render();const target=main.querySelector(`[data-key="${key}"]`);if(target)target.focus();}
  else if(action==='copy'){showToast('演示：未写入剪贴板。正式应用会在授权后复制，并按平台能力尝试清除。');}
  else if(action==='info')info(element.dataset.topic);
  else if(action==='lock')lock();
  else if(action==='unlock'){lockDialog.close();showToast('已进入界面演示；未进行真实身份验证。');}
  else if(action==='recovery'){showToast('没有万能主密码恢复。正式版本将指导核对密码库、密钥文件与可用备份。');}
  else if(action==='close-modal'){modal.close();if(state.lastFocus&&state.lastFocus.isConnected)state.lastFocus.focus();}
  else if(action==='add')addOrEdit();
  else if(action==='edit')addOrEdit(true);
  else if(action==='open-verification'){state.page='verify';state.filter='all';state.selection='github:totp';state.query='';document.getElementById('search').value='';render();}
  else if(action==='generator'){openModal('密码生成器 · 流程预览','<p>在创建或编辑条目时生成密码，再回填当前表单。正式实现使用系统安全随机源。</p><div class="demo-output">DEMO-only-not-a-real-secret</div><div class="notice">固定演示文本，不要把它当密码。正式版本支持长度、字符类型、短语模式，不默认保存生成历史。</div><div class="modal-actions"><button class="primary" data-action="edit">返回编辑流程</button></div>');}
  else if(action==='save-explanation'){openModal('保存之前，先保证可恢复','<p>校验字段 → 检查文件版本 → 生成加密新库 → 写入并验证 → 原子替换 → 保留加密备份。</p><div class="notice">此原型没有保存任何内容。正式版本本地保存成功后显示“已保存”，远端条件提交成功后才显示“已同步”。</div><div class="modal-actions"><button class="primary" data-action="close-modal">完成预览</button></div>');}
});
document.getElementById('search').addEventListener('input',(event)=>{state.query=event.target.value;state.selection=null;state.revealed.clear();document.body.classList.remove('detail-open');render();});
document.addEventListener('keydown',(event)=>{if((event.metaKey||event.ctrlKey)&&event.key.toLowerCase()==='k'&&!lockDialog.open&&!modal.open){event.preventDefault();document.getElementById('search').focus();}if(event.key==='Escape'&&!modal.open&&!lockDialog.open){document.body.classList.remove('detail-open');state.revealed.clear();render();}});
lockDialog.addEventListener('cancel',(event)=>event.preventDefault());
hydrateIcons();render();
