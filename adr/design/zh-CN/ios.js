'use strict';
// 设计演示：不请求网络，不读写密码库、设备凭据、剪贴板或持久化存储。
const paths = {
  password:'<rect x="5" y="10" width="14" height="11" rx="3"/><path d="M8 10V7a4 4 0 0 1 8 0v3M12 15v2"/>',
  verify:'<path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6l8-3Z"/><path d="m8 12 3 3 5-6"/>',
  identity:'<rect x="3" y="5" width="18" height="14" rx="3"/><circle cx="8" cy="10" r="2"/><path d="M5 16c0-3 6-3 6 0M15 10h3M15 14h3"/>',
  bank:'<rect x="3" y="5" width="18" height="14" rx="3"/><path d="M3 10h18M7 15h4"/>',
  settings:'<path d="M4 7h16M4 17h16"/><circle cx="9" cy="7" r="3"/><circle cx="15" cy="17" r="3"/>',
  key:'<circle cx="8" cy="9" r="5"/><path d="m12 13 8 8m-4-4 3-3m-1 5 3-3"/>',
  arrow:'<path d="m9 5 7 7-7 7"/>', back:'<path d="m15 5-7 7 7 7"/>',plus:'<path d="M12 5v14M5 12h14"/>',
  file:'<path d="M6 3h9l4 4v14H6V3Z"/><path d="M14 3v5h5M9 12h7M9 16h5"/>',
  sync:'<path d="M20 8A8 8 0 0 0 6 5L3 8M3 3v5h5M4 16a8 8 0 0 0 14 3l3-3M21 21v-5h-5"/>',
  cloud:'<path d="M7 18a5 5 0 1 1 0-10 6 6 0 0 1 11-1 5 5 0 0 1-1 11H7Z"/>',
  otp:'<circle cx="12" cy="13" r="8"/><path d="M9 2h6M12 8v5l3 2"/>',
  terminal:'<rect x="3" y="4" width="18" height="16" rx="3"/><path d="m7 9 3 3-3 3M13 15h4"/>',
  search:'<circle cx="10" cy="10" r="6"/><path d="m15 15 6 6"/>',
};
const icon=(name,cls='')=>`<svg class="${cls}" viewBox="0 0 24 24" aria-hidden="true">${paths[name]||paths.file}</svg>`;
const esc=(value)=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const NAV = [
  {id:'password',label:'密码'},
  {id:'verify',label:'验证'},
  {id:'identity',label:'证件'},
  {id:'bank',label:'银行'},
  {id:'settings',label:'设置'},
];
const state={tab:'password',stacks:Object.fromEntries(NAV.map(x=>[x.id,[{scene:x.id}]])),version:18,scope:'appfolder',theme:'dark',revealedFields:new Set(),returnFocus:null,
  filters:Object.fromEntries(NAV.map(x=>[x.id,{query:'',scope:'category',favorite:false,group:'all'}])),favorites:new Set(['developer','passport'])};
// 所有条目固定为合成数据。验证页只投影同一条目的能力，不复制凭据身份。
const DEMO_ITEMS = [
  {id:'developer',title:'开发账户',user:'user@example.invalid',category:'password',kind:'login',group:'开发工具',capability:'passkey'},
  {id:'mail',title:'私人邮箱',user:'mail@example.invalid',category:'password',kind:'login',group:'日常生活',capability:'otp'},
  {id:'note',title:'家庭网络备忘',user:'受保护备注与附件',category:'password',kind:'note',group:'日常生活'},
  {id:'server',title:'开发服务器',user:'dev@server.example.invalid',category:'verify',kind:'ssh',group:'开发工具'},
  {id:'passport',title:'护照',user:'个人证件 · 号码已隐藏',category:'identity',kind:'identity',group:'出行'},
  {id:'identity',title:'身份证',user:'个人证件 · 号码已隐藏',category:'identity',kind:'identity',group:'日常生活'},
  {id:'debit',title:'日常储蓄卡',user:'演示银行 · 尾号 0000',category:'bank',kind:'bank',group:'个人财务'},
  {id:'credit',title:'旅行信用卡',user:'演示银行 · 尾号 1111',category:'bank',kind:'bank',group:'个人财务'},
];
const KIND_NAMES={login:'登录信息',api:'API 凭据',note:'安全备注',passkey:'通行密钥',otp:'动态口令',ssh:'SSH 密钥',identity:'证件',bank:'银行卡'};
const screen=document.getElementById('screen');
const tabs=document.getElementById('tabs');
const dialog=document.getElementById('explanation');
const current=()=>state.stacks[state.tab].at(-1);
const row=(title,sub,route,kind='file',data='')=>`<button class="row" data-route="${route}" ${data}><span class="row-icon">${icon(kind)}</span><span class="row-body"><strong>${title}</strong><small>${sub}</small></span>${icon('arrow','chevron')}</button>`;
const group=(body)=>`<section class="group">${body}</section>`;
const heading=(title,sub='',add=false)=>`<div class="heading"><div><h1>${title}</h1>${sub?`<p>${sub}</p>`:''}</div>${add?`<button class="add-button" data-action="add" aria-label="新增条目流程说明">${icon('plus')}</button>`:''}</div>`;
const notice=(body,warning=false)=>`<div class="notice ${warning?'warning':''}">${body}</div>`;
const primary=(label,action)=>`<button class="primary" data-action="${action}">${label}</button>`;
const secondary=(label,route)=>`<button class="secondary" data-route="${route}">${label}</button>`;
const field=(label,value,secret=false)=>{const shown=state.revealedFields.has(label);return `<div class="field"><div><small>${label}</small><div class="field-value ${secret?'mono':''}">${secret&&!shown?'•••• •••• ••••':value}</div></div>${secret?`<button data-action="reveal" data-field="${esc(label)}" aria-pressed="${shown}" aria-label="${shown?'隐藏':'显示'}${esc(label)}（演示）">${shown?'隐藏':'显示'}</button>`:''}</div>`;};
const staticField=(label,value)=>`<div class="field"><div><label>${label}<input disabled value="${esc(value)}"></label></div></div>`;
const step=(text)=>`<div class="step">${text}</div>`;

function overview(scene){
  if(scene!=='settings')return catalogue(scene);
  return heading('设置','当前设备与密码库，分别管理')+
    group(row('同步与备份','尚未配置 · WebDAV / OneDrive','sync','sync')+row('系统密码与验证','自动填充、通行密钥与动态口令','system','verify')+row('密码库与高级信息','KDBX 4.1 · 演示文件','advanced','password'))+
    group(row('回收站','恢复与永久删除的边界','trash','file')+row('解锁与隐私','主密码、设备认证与授权期限','locked','password')+row('查看系统请求流程','密码选择、创建与使用通行密钥','ext-password','key'))+
    notice('此处不显示假开关。系统提供者和云同步状态应由真实平台探针确认。');
}
function detail(kind='login'){
  const names={login:'开发账户',passkey:'通行密钥',otp:'动态口令',ssh:'SSH 密钥',identity:'证件详情',bank:'银行卡详情',note:'安全备注'};
  const entry=DEMO_ITEMS.find(x=>x.id===current().entryId);
  let content='';
  if(kind==='passkey')content=`<span class="badge purple">记录已识别 · 系统尚未接入</span>`+group(field('所属网站 / RP ID','example.invalid')+field('账户','user@example.invalid')+field('存储位置','个人密码库 · KDBX'))+notice('软件私钥在库内保护。不能通过通用文本编辑器修改协议字段，也不会复制私钥到剪贴板。')+secondary('预览系统使用流程','ext-assert')+secondary('预览系统创建流程','ext-create');
  else if(kind==='otp')content=`<div class="group"><div class="otp">123 456<small>固定演示码，不用于登录</small></div></div>`+notice(state.version>=18?'iOS 18+ 动态口令系统填充属于待实现增强，当前未连接系统。':'iOS 17 保留库内动态口令；系统动态口令提供者增强需要 iOS 18+。');
  else if(kind==='ssh')content=group(field('密钥类型','Ed25519 · 示例')+field('私钥','DEMO-NOT-A-KEY',true))+notice('手机端保管 SSH 密钥。桌面端另接 KeeAgent 数据兼容与 SSH 代理，不承诺手机为任意 App 提供常驻代理。');
  else if(kind==='identity'||kind==='bank')content=group(field(kind==='bank'?'持卡人':'持有人','演示用户',true)+field(kind==='bank'?'完整卡号':'证件号码','DEMO-0000-0000',true)+field('有效期','2030年12月 · 示例'));
  else content=group(field('账户',entry?esc(entry.user):'user@example.invalid')+field(kind==='note'?'备注':'密码','DEMO-only-not-a-secret',true)+field('网站','example.invalid'))+((!entry||entry.capability==='passkey')?secondary('关联通行密钥','passkey-detail'):'');
  return heading(entry?esc(entry.title):(names[kind]||'条目详情'),'合成条目 · 不包含真实秘密')+content+`<div class="entry-actions">${secondary('编辑条目','editor')}${secondary('更多操作','item-actions')}</div>`+group(row('高级属性','自定义字段、保护标志与协议信息','advanced','settings')+row('附件与历史','演示文件 · 保留历史引用','attachments','file'));
}

function catalogue(scene){
  const filter=state.filters[state.tab];
  const title=NAV.find(x=>x.id===scene)?.label||'密码';
  return heading(title,'个人密码库 · 所有操作仅使用合成数据',true)+
    `<label class="catalogue-search">${icon('search')}<span class="sr-only">搜索条目</span><input id="catalogue-query" type="search" autocomplete="off" spellcheck="false" placeholder="${filter.scope==='all'?'搜索当前库全部分类':'搜索当前分类'}" value="${esc(filter.query)}"></label>`+
    `<div class="catalogue-filters"><button data-action="favorite-filter" aria-pressed="${filter.favorite}">${filter.favorite?'已选收藏':'收藏'}</button><label><span class="sr-only">搜索范围</span><select id="catalogue-scope"><option value="category" ${filter.scope==='category'?'selected':''}>当前分类</option><option value="all" ${filter.scope==='all'?'selected':''}>全部分类</option></select></label><label><span class="sr-only">分组筛选</span><select id="catalogue-group">${[['all','全部分组'],['开发工具','开发工具'],['日常生活','日常生活'],['出行','出行'],['个人财务','个人财务']].map(([key,label])=>`<option value="${key}" ${filter.group===key?'selected':''}>${label}</option>`).join('')}</select></label></div>`+
    `<div id="catalogue-results">${catalogueResults(scene)}</div>`+
    notice('列表不展开密码、证件号或私钥。生成器在编辑流程中；同一条目的验证信息不重复存储。')+
    (scene==='password'?secondary('查看同步与备份','sync'):'');
}
function catalogueResults(scene){
  const filter=state.filters[state.tab];
  const words=filter.query.trim().toLocaleLowerCase('zh-CN').split(/\s+/).filter(Boolean);
  const rows=DEMO_ITEMS.flatMap(entry=>{
    if(filter.scope!=='all'&&scene==='verify')return entry.capability?[{...entry,kind:entry.capability}]:entry.category==='verify'?[entry]:[];
    return filter.scope==='all'||entry.category===scene?[entry]:[];
  }).filter(entry=>(!filter.favorite||state.favorites.has(entry.id))&&(filter.group==='all'||entry.group===filter.group)&&words.every(word=>[entry.title,entry.user,entry.group,KIND_NAMES[entry.kind]].join(' ').toLocaleLowerCase('zh-CN').includes(word)));
  const status=`<p class="catalogue-count" role="status">${filter.scope==='all'?'当前库全部分类':'当前分类'} · ${rows.length} 个结果${filter.favorite?' · 仅收藏':''}</p>`;
  if(!rows.length)return status+`<div class="empty-results"><h2>没有找到匹配条目</h2><p>试试其他名称，或清除收藏与分组条件。</p><button class="secondary" data-action="clear-filters">清除筛选</button></div>`;
  return status+group(rows.map(entry=>row(esc(entry.title),`${esc(entry.user)} · ${KIND_NAMES[entry.kind]}${state.favorites.has(entry.id)?' · 收藏':''}`, 'detail',entry.kind==='login'?'key':entry.kind,`data-kind="${entry.kind}" data-entry="${entry.id}"`)).join(''));
}
function templates(){
  const choices=state.tab==='verify'?['otp','ssh','passkey']:state.tab==='identity'?['identity']:state.tab==='bank'?['bank']:['login','api','note'];
  return heading('新建条目','根据当前分类选择类型')+group(choices.map(kind=>row(KIND_NAMES[kind],kind==='passkey'?'需要网站发起合法创建请求':'分组表单 · 只读布局演示',kind==='passkey'?'passkey-create-info':'editor',kind==='login'?'key':kind,`data-kind="${kind}"`)).join(''))+notice('本原型不接受真实秘密。正式版填写后先保存到本机，再单独显示同步状态。');
}
function editor(){
  const kind=current().kind||'login';
  const entry=DEMO_ITEMS.find(x=>x.id===current().entryId);
  if(kind==='passkey')return heading('通行密钥不可随意改写')+notice('协议字段只读；修改凭据必须走专用、经过验证的管理流程。不能用普通表单重建网站绑定。')+secondary('查看高级属性','advanced');
  const extra=['login','api'].includes(kind)?staticField('账户','demo@example.invalid')+staticField('密码 / 令牌','固定演示，不接受真实秘密')+staticField('网站 / 应用','https://example.invalid'):staticField('受保护内容','固定演示，不接受真实秘密');
  return heading('编辑条目',`${KIND_NAMES[kind]||'条目'} · 只读布局演示`)+group(staticField('名称',entry?.title||'演示条目')+extra)+
    (['login','api'].includes(kind)?secondary('在密码字段中生成','generator-preview'):'')+
    group(staticField('分组',entry?.group||'未分组')+field('收藏',entry&&state.favorites.has(entry.id)?'已收藏 · 示例':'未收藏 · 示例'))+
    group(row('自定义字段','文本、秘密、布尔与引用映射','custom-fields','settings')+row('网站匹配与再次验证','按平台能力执行，不是额外加密','uri-rules','verify'))+
    primary('查看保存流程','save-layout')+`<button class="secondary" data-action="back">取消预览</button>`;
}
function itemActions(){
  const entry=DEMO_ITEMS.find(x=>x.id===current().entryId);
  return heading('更多操作',entry?esc(entry.title):'当前演示条目')+
    group(row('编辑条目','生成器在字段上下文内','editor','settings')+row('网站与匹配规则','多URI与真实来源检查','uri-rules','verify')+row('附件与历史','查看附件和历史引用','attachments','file'))+
    (entry?`<button class="secondary" data-action="favorite-item" aria-pressed="${state.favorites.has(entry.id)}">${state.favorites.has(entry.id)?'取消收藏':'加入收藏'}（仅演示）</button>`:'')+
    `<button class="secondary" data-action="copy-field">复制字段的授权说明</button><button class="secondary" data-action="clone-item">复制为新条目 · 说明</button>`+
    `<button class="secondary danger-action" data-action="trash-item">移到回收站 · 说明</button>`+secondary('查看回收站入口','trash');
}
function mobileScene(scene){
  if(scene==='new-item')return templates();
  if(scene==='editor')return editor();
  if(scene==='item-actions')return itemActions();
  if(scene==='generator-preview')return heading('密码生成器','生成后回填草稿，不自动修改网站密码')+group(field('示例内容','DEMO-only-not-a-secret',true))+notice('正式生成器使用安全随机源。替换已有口令需明确确认；保存与网站改密是两个操作，生成历史默认不持久化。')+`<button class="secondary" data-action="back">返回编辑</button>`;
  if(scene==='uri-rules')return heading('网站匹配与再次验证')+group(field('网站 / URI','https://example.invalid')+field('匹配策略','按当前平台提供的信息验证')+field('敏感操作','可要求新鲜授权 · 待实现'))+notice('iOS键盘候选和最终填充校验不是同一层；Android也未必提供完整路径和端口。严格规则无法验证时，不静默放宽。')+notice('再次验证不是额外加密，不能强制其他KDBX客户端执行；不能扩大Passkey的RP边界。');
  if(scene==='custom-fields')return heading('自定义字段','呈现类型与KDBX存储映射分开')+group(field('文本','演示标签')+field('秘密字段','DEMO-FIELD',true)+field('布尔型','是 · 布局示例')+field('引用','关联已有字段，不复制值'))+notice('字段类型需经KDBX映射验证。未知协议字段保持只读；不承诺移动系统能自动填充任意自定义字段。');
  if(scene==='trash')return heading('回收站','与备份、条目历史分别管理')+notice('本原型没有删除条目。正式版移入KDBX回收站后可恢复；永久删除需二次确认，并说明历史与备份仍可能保存旧数据。')+notice('不照搬依赖服务器的30天清理策略；按库设置和可恢复性规则执行。');
  return null;
}
function advanced(){return heading('高级属性','保留完整 KDBX 语义，不丢弃未知信息')+group(field('格式','KDBX 4.1 · 示例')+field('条目身份','UUID 保留；分类只是视图')+field('自定义受保护字段','DEMO-FIELD-VALUE',true))+`<p class="section-label">协议属性 · 只读</p>`+group(`<div class="field"><div><small>通行密钥私钥</small><div class="field-value">受保护 · 不展示原文</div><div class="raw-key">KPEX_PASSKEY_PRIVATE_KEY_PEM</div></div></div><div class="field"><div><small>兼容字段</small><div class="field-value">旧别名与未知属性保留</div><div class="raw-key">KPEX_PASSKEY_CREDENTIAL_ID<br>KPEX_PASSKEY_USER_HANDLE</div></div></div>`)+notice('Protected 是字段内层保护，不是独立权限。普通字段同样在加密库内。未知属性不能因为界面暂不支持就被删除。')+secondary('查看附件与历史引用','attachments');}
function attachments(){return heading('附件与历史','文件随 KDBX 加密保存与同步')+group(row('恢复说明.txt','2 KB · 示例元数据，无真实文件','attachment-info','file')+row('证件备份.pdf','480 KB · 示例元数据，无真实文件','attachment-info','file'))+notice('<strong>删除当前引用，不等于清除历史</strong><br>旧版本仍引用的附件继续保留。预览与导出须单独授权；扩展不加载附件预览。')+primary('预览附件操作说明','attachment')+secondary('查看扩展资源不足状态','ext-error');}
function sync(){return heading('同步与备份','当前密码库仅保存在本机')+`<div class="status-card"><span class="badge green">尚未配置</span><strong>选择一个双向同步源</strong><p>只传输加密 KDBX。本机备份与跨设备同步分别管理。</p></div>`+group(row('WebDAV','自己的服务器或兼容服务','webdav','cloud')+row('OneDrive','Microsoft 账户 · 优先应用目录','onedrive','cloud')+row('从“文件”打开','系统文件提供者 · 与直连区分','files','file'))+secondary('预览同步冲突','conflict')+notice('同一库不同时启用多个双向同步引擎。后台时机由系统决定，不保证每隔几分钟同步。');}
function webdav(){return heading('WebDAV','连接成功与版本保护，分别验证')+group(staticField('服务地址','https://dav.example.invalid')+staticField('目标文件','/keex/个人密码库.kdbx')+staticField('用户名','演示账户')+staticField('服务凭据','请勿输入真实密码'))+group(field('连接状态','未连接 · 设计示意')+field('条件写入保护','尚未验证'))+notice('真实实现需核对版本和 If-Match。服务忽略条件时保留冲突副本，不自动覆盖。')+primary('预览连接验证流程','webdav')+secondary('查看版本冲突','conflict');}
function onedrive(){return heading('OneDrive','让授权范围与使用场景一致')+`<p class="section-label">保存位置</p>`+group(`<button class="choice" data-scope="appfolder" aria-pressed="${state.scope==='appfolder'}"><span class="selection" aria-hidden="true"></span><span><strong>应用专用目录</strong><small>默认评估 Files.ReadWrite.AppFolder</small></span></button><button class="choice" data-scope="existing" aria-pressed="${state.scope==='existing'}"><span class="selection" aria-hidden="true"></span><span><strong>选择已有密码库</strong><small>目录范围与附加授权需单独确认</small></span></button>`)+notice(state.scope==='appfolder'?'个人与工作/学校账户分别验证最小权限。应用目录不代表任意已有文件都可访问。':'读取已有任意目录可能需要更大授权范围；不能把选中文件说成系统只授予该文件权限。',state.scope==='existing')+group(field('Microsoft 账户','尚未授权')+field('最终提交保护','尚未完成并发验证'))+primary('预览 Microsoft 授权说明','onedrive')+secondary('重新授权 / 离线状态说明','auth-required')+notice('本页不发起 OAuth，不读取账户或文件。登录云服务不需要密码库主密码。');}
function files(){return heading('从“文件”打开','外部文件绑定与导入副本不能混淆')+group(row('打开并绑定外部文件','后续访问依赖系统文件授权','file-info','file')+row('导入为 keex 管理的库','明确创建独立本机副本','file-info','password'))+notice('不能同时用文件提供者与 Graph 直连写同一个 OneDrive 对象。无法验证扩展写入时，关闭创建通行密钥入口。',true);}
function conflict(){return heading('保留双方修改','远端版本已变化 · 示例冲突')+`<span class="badge warning">等待处理 · 没有覆盖任何内容</span>`+group(`<div class="conflict-version">${icon('identity')}<div><strong>本机版本</strong><small>修改了开发账户 · 示例<br>仅本机已保存，尚未同步</small></div></div><div class="conflict-version">${icon('cloud')}<div><strong>远端版本</strong><small>另一台设备更新了相同条目<br>需要核对共同祖先</small></div></div>`)+notice('不能仅按时间较新覆盖。相同通行密钥身份出现不同私钥时，暂停使用并单独解决。',true)+primary('保留双方 · 流程说明','conflict')+`<button class="secondary" data-action="back">稍后处理</button>`;}
function system(){return heading('系统密码与验证','能力探针未接入，以下为版本设计')+group(field('密码与通行密钥提供者','尚未启用 · 原型')+field('当前模拟系统',`iOS ${state.version}`))+group(row('启用系统提供者','按系统设置完成授权，返回后复查','guide','verify')+row('动态口令系统填充',state.version>=18?'iOS 18+ 增强 · 待实现':'需要 iOS 18+ · 当前不可用','otp-info','otp')+row('管理器之间迁移',state.version>=26?'iOS 26+ 增强 · 待验证':'需要 iOS 26+ · 当前不可用','exchange','sync'))+notice('候选索引仅包含必要的账户/网站提示，不保存密码或私钥。关闭提供者应清理索引，但不删除库内凭据。')+secondary('预览密码填充请求','ext-password')+secondary('预览通行密钥创建','ext-create');}
function guide(){return heading('启用 keex','真实授权由 iOS 系统设置完成')+`<div class="steps">${step('在当前系统的密码自动填充设置中选择 keex；入口随版本变化。')}${step('确认允许展示哪些密码库的账户与网站候选，不需要停用其他管理器。')}${step('返回 keex，重新读取系统状态；未启用就继续显示未启用。')}</div>`+notice('正式应用仅使用受支持的公开入口。本页不跳转私有设置 URL，也不会伪造启用成功。')+primary('查看设置跳转说明','guide');}
function exchange(){return heading('迁移凭据','一次迁移，不是云同步')+notice(state.version>=26?'iOS 26+ 的系统凭据交换仍须接入与互通验证。原型不访问其他管理器。':'当前模拟版本未达到 iOS 26，本能力不开放。',state.version<26)+`<div class="steps">${step('用户主动选择来源与目标管理器。')}${step('由系统确认用户意图并完成必要设备认证。')}${step('校验传入数据后，原子导入 KDBX；未完成前保留原数据。')}</div>`+`<button class="primary" data-action="exchange" ${state.version<26?'disabled':''}>${state.version<26?'当前模拟版本不可用':'预览迁移安全边界'}</button>`;}
function extension(scene){
  const create=scene==='ext-create';const password=scene==='ext-password';
  const title=create?'创建通行密钥':password?'选择要填充的账户':'使用通行密钥';
  return `<div class="extension-label">${icon('verify')}原生扩展流程示意 · 非系统对话框</div>`+heading(title,'只处理当前网站的请求')+`<div class="request-target"><span class="badge">合成请求</span><p>请求网站</p><strong>example.invalid</strong><p>user@example.invalid</p></div>`+group(field('目标密码库','个人密码库 · 示例')+field('请求类型',create?'注册新凭据':password?'返回密码':'生成断言签名'))+(create?notice('先完成本地 KDBX 持久化，再向系统返回。远端同步稍后进行，不能把内存暂存当成保存成功。'):notice(password?'正式实现会核对来源和条目授权。本示意不返回或复制任何密码。':'私钥不离开受保护核心，返回的是本次请求的签名；这不是把私钥填进网页。'))+primary(create?'查看创建与保存顺序':password?'预览授权后填充':'预览设备授权与签名',create?'create-passkey':password?'fill-password':'assert-passkey')+secondary('查看无法安全保存的情况','ext-error')+`<button class="secondary" data-action="exit-extension">取消并返回主应用</button>`;
}
function renderScene(scene){
  const mobile=mobileScene(scene);if(mobile!==null)return mobile;
  if(NAV.some(x=>x.id===scene))return overview(scene);
  if(scene==='detail')return detail(current().kind);
  if(scene==='passkey-detail')return detail('passkey');
  if(scene==='advanced')return advanced();if(scene==='attachments')return attachments();
  if(scene==='sync')return sync();if(scene==='webdav')return webdav();if(scene==='onedrive')return onedrive();if(scene==='files')return files();if(scene==='conflict')return conflict();
  if(scene==='system')return system();if(scene==='guide')return guide();if(scene==='exchange')return exchange();
  if(['ext-password','ext-create','ext-assert'].includes(scene))return extension(scene);
  if(scene==='ext-error')return `<div class="extension-label">${icon('verify')}原生扩展异常示意</div>`+heading('暂时无法安全保存','可能是只读库、并发修改或资源不足')+notice('<strong>没有返回创建成功</strong><br>保留原有密码库，不降低 KDF，不在后台等待主程序替未保存的私钥兜底。',true)+group(field('本地写入','未完成 · 不继续注册')+field('可恢复操作','回主应用检查库与可用资源'))+primary('返回主应用处理','exit-extension')+`<button class="secondary" data-action="back">返回请求</button>`;
  if(scene==='locked')return `<div class="center"><div class="hero-icon">${icon('password')}</div>${heading('密码库已锁定')}<p class="caption">正式应用需主密码或已授权设备认证。<br>当前仅为锁定界面演示。</p></div>`+group(staticField('主密码','请勿在原型中输入真实密码'))+primary('返回演示密码库','unlock')+notice('锁定必须撤销读取、填充和签名授权，不能只遮住页面。本页没有真实加密或认证。');
  return heading('流程说明')+notice('此流程尚未接入真实平台。');
}
const explanations={
  'passkey-create-info':['先由网站发起请求','通行密钥不能像普通备注一样手工造一段字符串。正式版本接收合法网站/应用的系统创建请求，授权后持久化；本页没有生成密钥。'],
  'save-layout':['保存不是自动改网站密码','正式版先校验字段、保留旧版本，再原子提交KDBX；失败保留受授权的内存草稿。本原型字段只读，没有保存任何内容。'],
  'copy-field':['按字段单独授权和复制','显示、复制和自动填充是不同操作。正式版只复制所选字段，不一并复制OTP或恢复码。本原型没有写剪贴板。'],
  'clone-item':['先预览，再创建新条目','正式克隆使用新UUID，默认排除Passkey、OTP种子、恢复码、SSH私钥和未知插件秘密；普通口令复用另行确认。本次没有复制或写入任何凭据。'],
  'trash-item':['先移到回收站，再考虑永久删除','正式版可恢复条目并保留正确的历史与附件引用；云同步可能传播删除，备份需要独立保留。本次没有删除任何条目。'],
  add:['新增条目','从当前分类选择模板；生成器进入密码编辑器。原型不保存输入，也不接受真实主密码。'],
  attachment:['附件预览与导出','列表只有合成元数据，没有真实文件。正式实现先授权，再进行受控预览；外部分享会使秘密离开应用，必须明确确认。'],
  webdav:['连接与版本保护','先验证服务与目标，再在独立测试对象上验证条件写入。连接通不等于可以安全覆盖。本次没有发出请求。'],
  onedrive:['Microsoft 授权','正式应用通过原生公共客户端和系统浏览器进行授权码 + PKCE 登录，按选择的目录范围请求权限。本次没有登录、扩大权限或访问文件。'],
  conflict:['保留双方后再解决','正式实现保留两份完整加密 KDBX 与共同祖先，授权后比较；完成最终条件提交才显示同步成功。本次没有复制、合并或覆盖数据。'],
  guide:['系统设置入口','正式实现使用公开 API 或随版本更新的手动指引，并在返回后复查系统状态。本次没有更改系统设置。'],
  exchange:['凭据迁移','只在系统支持、用户确认和对端通过校验后导入。不会无提示枚举 Apple 密码或其他管理器。本次没有传输数据。'],
  'create-passkey':['本机保存早于返回','校验请求 → 用户授权 → 生成密钥 → 写入并验证 KDBX → 更新索引 → 返回响应 → 异步同步。本次未生成密钥，也未通知任何网站。'],
  'fill-password':['授权后才填充','实际来源与条目授权重新核对后，原生扩展经系统回传密码。本次仅展示顺序，没有执行 Face ID 或真实填充。'],
  'assert-passkey':['按请求签名','使用经过核对的 RP、凭据身份和原始请求 hash，完成必要授权与撤权检查。本次未执行认证或签名。'],
};
function explain(key){const [title,text]=explanations[key]||['尚未接入','当前仅为设计流程。'];state.returnFocus=document.activeElement;document.getElementById('explanation-title').textContent=title;document.getElementById('explanation-text').textContent=text;if(!dialog.open)dialog.showModal();}
function render(focus=false){
  const scene=current().scene;const ext=scene.startsWith('ext-');const locked=scene==='locked';
  document.querySelector('.preview').classList.toggle('extension',ext);document.querySelector('.preview').classList.toggle('is-locked',locked);
  tabs.hidden=ext||locked;tabs.innerHTML=NAV.map(x=>`<button class="tab" data-tab="${x.id}" ${state.tab===x.id?'aria-current="page"':''}>${icon(x.id)}<span>${x.label}</span></button>`).join('');
  document.getElementById('context').textContent=ext?'系统凭据请求 · 示意':'个人密码库 · 演示';
  document.getElementById('back').innerHTML=icon('back');document.getElementById('back').disabled=state.stacks[state.tab].length===1||locked;
  document.querySelector('.lock-button').innerHTML=icon('password');document.querySelector('.lock-button').disabled=locked;
  screen.innerHTML=renderScene(scene);document.documentElement.dataset.theme=state.theme;
  const scenario=document.getElementById('scenario');scenario.value=[...scenario.options].some(x=>x.value===scene)?scene:'';
  if(focus){screen.focus({preventScroll:true});window.scrollTo(0,0);}
}
function push(scene,kind,entryId){const parent=current();state.revealedFields.clear();state.stacks[state.tab].push({scene,kind:kind??parent.kind,entryId:entryId??parent.entryId});render(true);}
function back(){if(current().scene==='locked')return;if(state.stacks[state.tab].length>1)state.stacks[state.tab].pop();state.revealedFields.clear();render(true);}
function exitExtension(){while(state.stacks[state.tab].length>1&&current().scene.startsWith('ext-'))state.stacks[state.tab].pop();state.revealedFields.clear();render(true);}
document.addEventListener('click',event=>{
  const button=event.target.closest('button');if(!button||button.disabled)return;
  if(button.dataset.tab){state.tab=button.dataset.tab;state.revealedFields.clear();render(true);return;}
  if(button.dataset.scope){state.scope=button.dataset.scope;render();screen.querySelector(`[data-scope="${state.scope}"]`).focus();return;}
  if(button.dataset.route){const route=button.dataset.route;
    if(route==='passkey-create-info'){explain(route);return;}
    if(route==='attachment-info'){explain('attachment');return;}
    if(route==='file-info'){explain('guide');return;}
    if(route==='auth-required'){state.returnFocus=button;document.getElementById('explanation-title').textContent='云授权失效不等于密码库锁死';document.getElementById('explanation-text').textContent='本地可用密码库继续离线使用。交互重新授权放在主应用，不放在网站凭据扩展里。原型没有真实账户。';dialog.showModal();return;}
    if(route==='otp-info'){state.returnFocus=button;document.getElementById('explanation-title').textContent='动态口令系统填充';document.getElementById('explanation-text').textContent=state.version>=18?'iOS 18+ 增强仍待实现。seed保存在受保护字段中，系统索引不存seed。':'当前模拟为 iOS 17；本功能需要 iOS 18+。库内动态口令不因此消失。';dialog.showModal();return;}
    push(route,button.dataset.kind,button.dataset.entry);return;
  }
  const action=button.dataset.action;
  if(action==='add'){push('new-item');return;}
  if(action==='favorite-filter'){state.filters[state.tab].favorite=!state.filters[state.tab].favorite;render();screen.querySelector('[data-action="favorite-filter"]')?.focus();return;}
  if(action==='clear-filters'){state.filters[state.tab]={query:'',scope:'category',favorite:false,group:'all'};render();screen.querySelector('#catalogue-query')?.focus();return;}
  if(action==='favorite-item'){const id=current().entryId;if(id){state.favorites.has(id)?state.favorites.delete(id):state.favorites.add(id);render();screen.querySelector('[data-action="favorite-item"]')?.focus();}return;}
  if(button.id==='theme-button'){state.theme=state.theme==='dark'?'light':'dark';document.documentElement.dataset.theme=state.theme;return;}
  if(action==='back'){back();return;}
  if(action==='exit-extension'){exitExtension();return;}
  if(action==='lock'){Object.values(state.filters).forEach(filter=>{filter.query='';});push('locked');return;}
  if(action==='unlock'){state.stacks[state.tab]=[{scene:state.tab}];state.revealedFields.clear();render(true);return;}
  if(action==='reveal'){const key=button.dataset.field;state.revealedFields.has(key)?state.revealedFields.delete(key):state.revealedFields.add(key);render();[...screen.querySelectorAll('[data-action="reveal"]')].find(node=>node.dataset.field===key)?.focus();return;}
  if(action==='dismiss'){dialog.close();return;}
  if(action)explain(action);
});
dialog.addEventListener('close',()=>{if(state.returnFocus?.isConnected)state.returnFocus.focus();});
document.getElementById('version').addEventListener('change',event=>{state.version=Number(event.target.value);render();});
document.getElementById('scenario').addEventListener('change',event=>{const scene=event.target.value;state.tab=['password','verify'].includes(scene)?scene:'settings';state.stacks[state.tab]=[{scene:state.tab}];state.filters[state.tab]={query:'',scope:'category',favorite:false,group:'all'};if(scene!==state.tab)state.stacks[state.tab].push({scene});state.revealedFields.clear();render(true);});
screen.addEventListener('input',event=>{if(event.target.id==='catalogue-query'){state.filters[state.tab].query=event.target.value;document.getElementById('catalogue-results').innerHTML=catalogueResults(current().scene);}});
screen.addEventListener('change',event=>{if(event.target.id==='catalogue-scope'||event.target.id==='catalogue-group'){const id=event.target.id;state.filters[state.tab][id==='catalogue-scope'?'scope':'group']=event.target.value;render();document.getElementById(id)?.focus();}});
document.addEventListener('keydown',event=>{if(event.key==='Escape'&&!dialog.open&&current().scene!=='locked')back();});
render();
