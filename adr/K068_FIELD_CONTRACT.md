# K068：个人资料字段契约 v1

日期：2026-10-18。范围：可执行的**合成测试规格**，不是 Flutter/Rust 安全核心、生产 writer、迁移器或通知实现。主状态只看 [TASKS](TASKS.md) / [STATUS](STATUS.md)，验证记录见 [K068 证据](evidence/K068.md)。

本文件把 [领域规格](PERSONAL_VAULT_SPEC.md) 中的编码选择收敛为一套规则。完整字段名、中文标签、类型适用范围、枚举、保护策略和关系基数以 [contract.json](../tests/vault_domain/contract.json) 为唯一字典；行为校验在 [contract.py](../tests/vault_domain/contract.py)，反例在 [test_contract.py](../tests/vault_domain/test_contract.py)。后续 Dart/Rust 实现复用这些语义和样本，不把 Python 测试工具接进产品。

## 1. 标识、最小保存和原始数据

每条新资料仍是标准 KDBX Entry。XML UUID 保持 16 字节的标准 base64；本契约 JSON 内的 Entry 引用及关系/规则/事件 ID 使用同一原始字节的小写 32 位十六进制，不使用名称、号码、激活文本或文件路径作身份。全零 UUID 不作有效资料 ID；本地 VaultBindingId 不进入跨库强引用。

标记使用普通 String：keex.record.schema=1、keex.record.type=字典枚举。它们在 KDBX 的加密 XML 内，不写 PublicCustomData。类型/版本共同改变是显式类型迁移，不能分别自动合并。

最低保存只要求非空 Title、类型和版本；业务项均允许尚未填写。SIM/eSIM 可以没有号码、ICCID、EID、线路、安装设备或激活资料。未知、不适用、不完整由缺失和明确的状态表示，不填假值；新 UUID 和别名足以建立草稿。

| 输入情形 | 本轮检查结果 | 后续写入约束 |
| --- | --- | --- |
| 没有新领域标记或未知 keex 字段的旧条目（允许旧 parent 别名） | legacy；保留原字段、混合凭据和 UUID | 不自动补 marker、拆分 Passkey 或改变分类 |
| v1 且全部已知字段合法 | valid | 只表示规格通过；仍需会话、版本、G0/GV0 等门槛，不能据此开 writer |
| marker 缺一半、未来版本/类型/枚举 | read_only | 展示可识别摘要并保留所有原文，不能按 v1 重建 |
| 已知字段错误、未知 keex 字段或复合子字段 | read_only | 原值与保护属性保留，不清空、不删字段、不自动修正 |
| 非 keex 的外部自定义字段 | 原样保留；不自动进入摘要 | 由 K002/K003 验证完整无损，不能从表单字段重建全条目 |
| 缺失关系目标/未设置滚动依据或时区 | warning，保留数据 | 不同名重绑、不猜日期、不生成已确认调度 |

Record 只是测试适配结构。XML String 转成 map 前必须用 record_from_pairs 检查重复 Key；重复 JSON 成员也拒绝。否则后出现的值会静默覆盖前值。相同 Entry UUID 的当前条目必须诊断为冲突，历史版本不计作新的当前条目。

缺失字段表示尚未填写或不适用；文本空字符串是明确保存的空值；复合值不接受空字符串/null 代替缺失。后续 patch 必须区分 set 和 remove，设置空字符串不等于删除，null 不兼作多种动作。本轮没有实现 patch API。

## 2. 保护与显示

字典的 protected=true 是新写的最低要求；标准 Password、已知敏感业务字段即使被外部客户端改成未保护，运行时仍须显式揭示。原字段已受保护时不因字典允许摘要而降低显示策略；未知扩展默认不进入自动摘要。

检查器发现已知敏感字段未保护时返回 read_only；它不修改保护位。历史修正须明确操作并通过无损保存，不借改标题悄悄重写所有字段。显示卡号不同时揭示 CVV、PIN、激活码或附件。复合事实作为一个保存原子组，不等于其中所有信息可以一起展示。

所有字段都受整库加密。Protected 不是另一把密钥，也不构成浏览器内字段级密码学隔离。requires_reveal 仅用于验证显示分类，不是授权函数，不代替 VaultSession/epoch。

## 3. 精确金额和事实来源

金额只用严格十进制字符串，不经过浮点；保留小数位，不接受指数、NaN、Infinity、前导加号、无意义前导零或负零。当前测试能力界限是最多 38 位数字、18 位小数；超出界限保留只读，不四舍五入。币种清单在字典中，是本版明确验证的集合，不宣称覆盖全球币种；未知代码保留只读。

手工余额、限额、费用、套餐价格、剩余流量和服务状态都将值与依据一起存为一个 Protected JSON String。例如：

~~~json
{
  "amount": "19.90",
  "currency": "USD",
  "recordedAt": "2026-10-18T00:00:00Z",
  "source": "user_entry",
  "confidence": "user_asserted"
}
~~~

source 为 user_entry / user_verified / file_import；confidence 为 unknown / user_asserted / user_verified。user_verified 可信程度只能配手工核实来源；仍是用户记录，不是机构回执。可选 sourceReference 仅为加密引用，不自动访问。录入/导入不默认升级为已核实。

金额、币种、小数精度（由字符串保留）、记录时间、来源、可信程度与可选来源引用是**同一个原子值**。一端改金额、另一端改核实时间，必须保留冲突，不能拼成并不存在的核实事实。余量另有精确 value 和 byte/minute/message 单位；MB 等未约定单位不暗自换算。

订阅的 keex.subscription.billing 将金额、币种、完整 period 与来源一起原子化，防止混出新价格配旧计费周期。period 固定 unit(day/month/year)、正整数 interval、date/month 精度 anchor、overflow=clamp、可选 timeZone；按日重复必须有 date 精度锚点。缺时间配置不推导通知。套餐价格与其独立的激活、起止规则目前分字段，修改涉及多字段时须同一事务；不允许不同原子组的合并跳过最终业务约束检查。

## 4. 日期精度与时区

日期复合字段统一使用 precision/value；不是把所有日期变成 UTC 午夜。

| precision | value 词法 | 时区与边界 |
| --- | --- | --- |
| month | YYYY-MM | 仅年月，无时区/fold；卡到期只接受此精度，不声称银行月末某时一定停卡 |
| date | YYYY-MM-DD | 公历合法日期；可保存显式业务时区，不猜设备时区；不能有 fold |
| instant | YYYY-MM-DDTHH:mm:ss[.1至6位小数]Z | 明确 UTC，拒绝闰秒和隐含偏移；不再附加 timeZone/fold |
| local | YYYY-MM-DDTHH:mm:ss[.1至6位小数] | 必须有明确 IANA timeZone；重复时间必须显式 fold=0/1；不存在的时间拒绝 |

公历范围沿本测试运行时的 0001–9999，越界和时区转换溢出必须进入只读诊断，不能使检查器崩溃。ZoneInfo 使用执行环境的时区数据，没有联网或自动安装 tzdata；找不到时区即只读。真实跨端复现还要固定各运行时使用的时区数据，归 K077。

周期从**原锚点**计算：1 月 31 日的月付遇到 2 月可以截到月末，3 月仍回到 31 日；2 月 29 日按年重复在非闰年截至月末，到下一个闰年恢复。lead 的单位只允许 calendar_day，表示业务时区的日历日，不偷换成 24 小时。

本轮检查编码和 DST 本地时间合法性，**没有实现下一次到期计算或 OS 调度**。重复规则遇到不存在/重复本地时刻时，K077/K078 必须延续无法唯一确定则不猜的策略，要求显式确定后再调度。规则和其 anchor/due 已显式包含的时区冲突时只读；旅行不能悄悄改业务时区。

## 5. 有方向的关系和跨 ID 约束

每条关系单独占 keex.relation.RELATION_ID，Protected JSON 值为：

~~~json
{"type":"paidBy","target":"22222222222222222222222222222222","state":"active"}
~~~

可选 validFrom/validUntil 使用上节日期对象，必须可比较且开始不晚于结束。同关系的 type、target、state、作用期和未知子字段是整体。ID 不在值内重复，以免字段名和值身份冲突。

字典固定来源、目标和最多活动关系数。关键方向是：卡 belongsTo 账户；订阅 paidBy 卡/账户；线路 usesProfile 配置；线路/配置 usesPlan 套餐；订阅/线路/金融账户 serviceAccount 登录；维护事项 maintains 资料。反向索引内存派生，配置不再保存一条反向 usesProfile 副本。

关系状态为 active / historical / review。paidBy、belongsTo、usesProfile、replaces、maintains、credentialOf、serviceAccount 各自最多一条 active；即便 relationId 不同也互斥。历史边和待复核边不计为当前槽位。来源或目标类型不合、跨库 ID、自指、重复 ID 均不能悄悄接受。

不同 ID 的新增也须在合并后检查逻辑槽：两个离线设备分别新增付款卡 A/B，结果为显式冲突，不能生成两个当前付款方式。本轮检查器能拒绝这种候选状态，真正三方合并/事务仍归 K079/K083。

缺失目标保留为 warning，供恢复时按原 UUID 找回。有限的资料引用环不要求递归解引用；K073 实现遍历深度/节点数上限及循环检测。关系不授予签名、填充、支付或 eSIM 安装能力。

## 6. 旧 Passkey 和迁移边界

旧 keex.parentEntryUuid 继续保留。测试读取接受 32 位十六进制、标准连字符 UUID、规范 base64 的 16 字节表达，仅在内存比较其原始身份，不改写原值。新父关系使用 credentialOf，和金融 belongsTo 分开。已带 v1 类型的旧别名来源同样必须是 login；目标有已知类型时也必须是 login。无 marker 的旧混合条目不被强猜类型；未知 keex 字段即使单独出现也进入只读。

旧别名与新 active credentialOf 相同可作为同一聚合视图；不同则 read_only/待复核，保留双方，不选择更新的时间戳。旧的登录密码+KPEX 混合条目保持同一个 Entry，可产生多个能力视图；不重写 RP、credentialId、userHandle、私钥和历史。能力是否可用由凭据适配器判定，不由关系或 record.type 推断。

迁移流程仍是预览、加密备份、明确确认、同一保存事务、再读验证。本轮只固定规则：

- 整库复制保留库内 UUID/关系，重新建立本机绑定，不自动推断为同一同步源。
- 单条克隆新建 UUID，不改变其他条目指向原对象的入边；出边是否保留要在预览明确列出。
- 批量导入为选中的集合建立旧→新 ID 映射，只重映射该集合内可理解的引用；集合外引用明确选择保留/解除/待复核，不按同名猜测。
- 未知未来关系编码、类型或保护属性不能猜测迁移；版本/类型与受影响字段、关系一起事务处理。失败保留旧库和原字段。

## 7. 维护规则与事件

动态字段只属于 maintenance 类型，各用一个 Protected JSON String：

| 字段 | 必需内容 | 有意保留的未知 |
| --- | --- | --- |
| keex.lifecycle.rule.ID | version=1、revision、kind、enabled、来源与 recordedAt | 业务时区未设时警告，不产生调度 |
| once | 另需 due 日期对象 | 不猜额外机构规则 |
| calendar | 另需 anchor、unit(month/year)、interval、overflow=clamp | 保留原始锚点 |
| rolling | 另需 unit(day/month/year)、interval；可选 basisEventId | 无有效依据事件时截止未知 |
| manual_next | 可选 due | 未设置下一日期是合法的不完整状态 |
| keex.lifecycle.event.ID | version=1、kind、ruleId、ruleRevision、occurredAt、来源与 recordedAt | 发生时间不由录入时间替代 |

rule 可选 lead={unit:calendar_day,value:非负整数}、timeZone 和 sourceReference。事件 completed 必须有 effective 布尔值；retracted 必须引用 targetEventId。撤销保留原完成事件，不删历史；必须指向同规则、同规则版本的 completed 事件。依据事件不属于该规则时拒绝；被撤销、无效或缺失的依据不能变成已确认的滚动期限。点击通知/打开网页没有 completed 语义。

可选证据是 {entry:EntryUUID,attachment:附件Key}，仅引用库内标准附件；不是磁盘路径、联网 URL 或另一个明文主库。附件缺失与历史生命周期由 K024/K073 验证，本轮不导出或解析附件内容。

通知仍只包含随机调度 ID、触发时间和通用文案，不带 Entry UUID、标题、金额或激活资料；这些是 K078 的待实施契约，不是当前代码能力。

## 8. 验证入口与剩余门槛

在仓库根目录运行：

~~~sh
python3 -B -m unittest discover -s tests/vault_domain -p test_contract.py
~~~

K069 领域库矩阵另见 [测试入口](../tests/vault_domain/README.md)。K002 的 AES/Argon2、参考客户端来源缺口仍需补齐；领域样本不能代替算法或客户端来源覆盖。K001/K002 已登记的人工复核、K003 候选 writer 无损、G0/GV0 均没有因本契约自动通过。

测试预算限制仅防合成测试失控，不是产品容量承诺；1k/10k 条目、附件增长、iOS 扩展和浏览器资源仍须实测。所有样本均合成；没有接入真实库、账户或同步源。
