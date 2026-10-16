# iOS 设计验证记录

日期：2026-10-12。目标：`zh-CN/ios.html`。这是浏览器HTML原型，不是实际iOS App或凭据扩展。

## 复跑方式

在项目根目录执行：

```sh
node --check adr/design/zh-CN/ios.js
python3 adr/design/verify.py
python3 adr/design/verify_ios.py
python3 -m http.server 5173 --bind 127.0.0.1 --directory adr/design/zh-CN
```

浏览器打开本机5173的`/ios.html`。通过浏览器开发控制台或允许的浏览器工具加载本地测试脚本：

```javascript
const testScript = document.createElement('script');
testScript.src = 'tests/ios-checks.js';
testScript.onload = () => console.log(window.runKeexIosChecks());
document.head.append(testScript);
```

脚本仅模拟操作合成原型的DOM控件；不执行真实认证、网络同步或文件读写。脚本完成后返回密码根页面。调整视口后可直接再次调用 `runKeexIosChecks()`。验证后关闭服务。

## 实际结果

| 项目 | 结果 |
| --- | --- |
| JavaScript语法 | exit 0 |
| 原始资料与主任务校验 | 11个原始SHA-256未变；67个主任务唯一、无环；本地引用有效 |
| iOS专项静态校验 | 五tab顺序一致；24个子任务唯一且无环；19个来源ID均可解析；9个专项本地链接有效 |
| 1440×1000 | 同一组60项断言通过 |
| 390×844 | 同一组60项断言通过；底部导航为fixed；真实浏览器点击“验证”成功 |
| 320×740 | 同一组60项断言通过 |
| 844×390 | 同一组60项断言通过；Escape不能跳过锁定示意 |
| 浏览器控制台 | 最终0 error、0 warning |
| 清理 | 预览服务已停止，浏览器页面已关闭 |

60项检查覆盖根导航、二级返回、秘密显隐、只读演示输入、双云授权/冲突说明、版本门槛、扩展与主界面隔离、创建先持久化、异常状态、主题与13个场景横向布局。四个视口复跑产生240条成功断言，**不是240项不同的安全测试**。

## 发现并修复

第一次执行到扩展请求时失败：路由已经切换并隐藏tab，但renderScene没有调用扩展专用渲染函数。补充分派后重新加载页面，在上述四个视口全量通过。该问题属于原型路由，不是系统原生接口缺陷。

## 未验证

没有像素级视觉复核、原生Dynamic Type/VoiceOver、真实触屏/安全区、Flutter构建、iOS签名/entitlement、真实凭据服务、云账号/CAS或KDBX无损测试。浏览器断言不能证明这些能力，原生与协议任务均为TODO。

真实副作用按钮全部展示说明；不能据此声称已经登录Microsoft、写入附件、执行生物识别或创建Passkey。资料研究也不是参考项目全仓安全审计。
