'use strict';
// 仅由设计验证时主动加载。通过实际DOM控件执行，不读写主应用内部state。
window.runKeexIosChecks = function runKeexIosChecks() {
  const checks=[];
  const check=(name,value)=>{checks.push({name,passed:Boolean(value)});if(!value)throw new Error(name);};
  const click=(selector)=>{const node=document.querySelector(selector);if(!node)throw new Error(`找不到控件：${selector}`);node.click();};
  const choose=(scene)=>{const select=document.getElementById('scenario');select.value=scene;if(!select.value)throw new Error(scene);select.dispatchEvent(new Event('change',{bubbles:true}));};
  const version=(value)=>{const select=document.getElementById('version');select.value=String(value);select.dispatchEvent(new Event('change',{bubbles:true}));};
  const text=()=>document.getElementById('screen').textContent;
  const modal=()=>document.getElementById('explanation');
  if(modal().open)click('[data-action="dismiss"]');
  choose('password');
  check('页面中文',document.documentElement.lang==='zh-CN');
  check('五项导航顺序',[...document.querySelectorAll('#tabs span')].map(x=>x.textContent).join('、')==='密码、验证、证件、银行、设置');
  for(const [id,label] of [['password','密码'],['verify','验证'],['identity','证件'],['bank','银行'],['settings','设置']]){
    click(`[data-tab="${id}"]`);
    let guard=20;while(!document.getElementById('back').disabled&&guard-->0)click('#back');
    check(`${label}根页面`,document.querySelector('#screen h1').textContent===label);
    check(`${label}导航状态`,document.querySelector('#tabs [aria-current="page"]').dataset.tab===id);
  }
  choose('password');click('[data-route="detail"]');
  check('详情默认遮罩',text().includes('••••'));
  click('[data-action="reveal"]');check('显示的只有合成演示文本',text().includes('DEMO-only-not-a-secret'));
  click('[data-action="reveal"]');check('再次遮罩',!text().includes('DEMO-only-not-a-secret'));
  click('#back');check('二级返回原列表',document.querySelector('#screen h1').textContent==='密码');
  choose('advanced');check('KPEX高级字段可见',text().includes('KPEX_PASSKEY_PRIVATE_KEY_PEM'));
  check('未知属性保留说明',text().includes('未知属性不能'));
  choose('attachments');check('附件仅演示元数据',text().includes('无真实文件'));
  check('历史引用保护说明',text().includes('旧版本仍引用'));
  click('[data-action="attachment"]');check('附件操作未伪执行',modal().open&&modal().textContent.includes('没有真实文件'));click('[data-action="dismiss"]');
  choose('webdav');check('WebDAV真实凭据不可输入',[...document.querySelectorAll('#screen input')].length===4&&[...document.querySelectorAll('#screen input')].every(x=>x.disabled));
  check('WebDAV条件写入独立状态',text().includes('条件写入保护')&&text().includes('尚未验证'));
  click('[data-action="webdav"]');check('WebDAV操作未联网',modal().textContent.includes('没有发出请求'));click('[data-action="dismiss"]');
  choose('onedrive');click('[data-scope="appfolder"]');check('默认最小权限说明',text().includes('Files.ReadWrite.AppFolder'));
  click('[data-scope="existing"]');check('扩大权限需单独解释',text().includes('更大授权范围'));
  click('[data-action="onedrive"]');check('OAuth采用PKCE且未执行',modal().textContent.includes('PKCE')&&modal().textContent.includes('没有登录'));click('[data-action="dismiss"]');
  choose('conflict');check('冲突保留双方',text().includes('没有覆盖任何内容'));
  click('[data-action="conflict"]');check('原型不假装合并',modal().textContent.includes('没有复制、合并或覆盖'));click('[data-action="dismiss"]');
  version(17);choose('system');check('iOS17不宣称OTP提供者可用',text().includes('需要 iOS 18+'));
  click('[data-route="exchange"]');check('iOS17迁移入口禁用',document.querySelector('#screen .primary').disabled);
  version(26);check('iOS26迁移仅预览',!document.querySelector('#screen .primary').disabled&&text().includes('仍须接入'));
  click('[data-action="exchange"]');check('不枚举其他密码管理器',modal().textContent.includes('无提示枚举'));click('[data-action="dismiss"]');
  version(18);
  for(const [scene,title] of [['ext-password','选择要填充的账户'],['ext-create','创建通行密钥'],['ext-assert','使用通行密钥']]){
    choose(scene);check(`${title}没有主应用导航`,document.getElementById('tabs').hidden);
    check(`${title}明确为示意`,text().includes('非系统对话框'));
  }
  choose('ext-create');click('[data-action="create-passkey"]');check('先持久化后返回',modal().textContent.includes('写入并验证 KDBX → 更新索引 → 返回响应'));click('[data-action="dismiss"]');
  choose('ext-error');check('写入失败不返回成功',text().includes('没有返回创建成功'));
  click('[data-action="exit-extension"]');check('扩展退出恢复主应用导航',!document.getElementById('tabs').hidden);
  choose('password');click('[data-route="detail"]');click('[data-action="reveal"]');click('.lock-button');
  check('锁定移除秘密显示',!text().includes('DEMO-only-not-a-secret')&&text().includes('密码库已锁定'));
  check('锁定不展示主导航',document.getElementById('tabs').hidden);
  click('[data-action="unlock"]');check('演示解锁返回主界面',!document.getElementById('tabs').hidden);
  const initial=document.documentElement.dataset.theme;click('#theme-button');check('切换主题',document.documentElement.dataset.theme!==initial);click('#theme-button');
  for(const scene of ['password','verify','sync','webdav','onedrive','conflict','system','advanced','attachments','ext-password','ext-create','ext-assert','ext-error']){
    choose(scene);check(`${scene}无横向溢出`,document.documentElement.scrollWidth<=innerWidth);
  }
  choose('password');
  check('无第三方网络资源',performance.getEntriesByType('resource').every(x=>new URL(x.name).origin===location.origin));
  const report={viewport:[innerWidth,innerHeight],passed:checks.filter(x=>x.passed).length,failed:checks.filter(x=>!x.passed).length,checks,scope:'HTML设计交互，不是原生凭据/云同步测试'};
  window.__keexIosReport=report;
  return report;
};
