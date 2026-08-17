# Stage 06 — 语义诊断与 OpenAI 模型路由详细设计

| 字段 | 内容 |
| --- | --- |
| 状态 | 本地开发性提供商路径已实现；资格验证待完成 |
| 设计版本 | 0.5 |
| 日期 | 2026-08-17 |
| 规范文本 | [英文版](stage-06-semantic-and-model-routing-design.md) |
| 依据 | [Stage 01](product-requirements.zh-CN.md)、[Stage 02](conflict-taxonomy-and-golden-examples.zh-CN.md)、[Stage 03](detailed-design-and-architecture.zh-CN.md)、[Stage 04](test-scenarios-and-quality-gates.zh-CN.md) |

## 1. 目标与当前边界

本设计把模型选择改成“按能力路由、来源可追溯、允许用户覆盖、可随官方资料更新”，而
不是把“版本号最大”硬编码成“能力最强”。它还把本地开发性语义诊断实现为可以逐步
评审的垂直切片。

当前工作树已经实现安全的路由基础：

- 一份附官方资料摘要的、已评审 OpenAI 模型能力 profile；
- 支持 `auto` 与精确用户 pin 的离线路由器；
- 把账号可用性、官方推荐和产品资格验证分别表示；
- 质量优先语义推理的当前默认值；
- 只读的官方文档漂移检查；
- 十一个可执行的模型路由场景；
- 每周运行的 GitHub Actions profile 监测；
- Codex PR advisory review 的模型与 effort 用户覆盖项；
- 排除秘密与脚本的确定性语义披露代理；
- 与 manifest digest 精确绑定的授权及失效规则；
- 使用已登录 Codex Desktop、拒绝任何已观察工具调用的 ephemeral 适配器；
- 确定性的边界感知候选检索：先保留 trigger、委派、负路由及其相邻证据，再优先选择
  相关 Skill 对/维度；同分时平衡来源，明确检索信息只用于选择，并显式记录截断；
- 两个并行盲审分析者，随后由第三个全新上下文的仲裁者处理；
- 封闭且强制引用的响应契约与有边界的建议契约；
- 写入同一封存结果图的本地语义裁决。

语义覆盖默认开启，用户可以显式关闭、缩小范围或排除精确来源。用户显式发起完整语义
诊断时，默认运行有边界的 provider panel，并只授权紧接着生成的单次 manifest；普通
确定性 `scan` 绝不启动 provider。独立调用仍需确认精确 digest。没有任何
provider/model/adapter/prompt 身份完成 Stage 04 资格协议，因此成功运行不代表准确率、
校准、有用性或发布就绪。它使用已登录的 Codex Desktop 账号，不需要 OpenAI API key；
也不能据此推断另一个 API 项目可用该模型。

## 2. 四类事实必须保持独立

模型路由同时使用四类事实，但不能把它们压成一个“最佳模型”结论：

| 事实 | 来源 | 能证明什么 | 不能证明什么 |
| --- | --- | --- | --- |
| 官方推荐 | 已评审的 OpenAI 文档 profile | OpenAI 当前把某模型描述为某项能力的推荐选择 | 当前 API 项目可用、Agent Doctor 准确、成本适合或未来行为 |
| 账号可用性 | 认证后的 `GET /v1/models` 快照 | 在观察时刻，该 API 项目可见某个精确 model ID | 哪个模型最强、端点权限、quota 或资格验证 |
| 产品资格 | Stage 04 holdout 与绝对门禁 | 某一 provider/model/adapter/prompt 契约满足声明的证据协议 | 其他模型、后续行为或变化后的 prompt/profile 同样合格 |
| 用户策略 | CLI/config/GitHub variable | 用户选择了 `auto`、某能力档或精确 pin | 该选择实际可用、兼容或已通过资格验证 |

路由器只对这四项做交集判断。它不按型号字符串排序，不把创建时间当质量，也不把
`/v1/models` 的第一项当官方推荐。

## 3. 动态选择的生命周期

这里的“动态”是受控更新闭环，不是运行时盲读网页：

```text
官方 Markdown 发生变化
        |
        v
资料漂移报告 ----------> 无法检查资料时属于执行失败
        |
        v
候选 profile diff
        |
        +--> 来源与能力评审
        +--> 路由契约测试
        +--> 若用于产品 finding，则运行语义 holdout 资格验证
        |
        v
通过 PR 晋升为已评审 profile
        |
        v
运行时路由 + 账号可用性 + 用户策略
```

每周的 `OpenAI model profile watch` workflow 只抓取 allowlist 内的官方 Markdown，核对
内容摘要和受约束的机器可读字段，并保存漂移报告。退出码 `2` 表示报告有效，但需要政策
评审；退出码 `3` 表示检查没有完成，此时任何推荐都不能被改动。该 workflow 只有仓库
读权限，也不需要 API key。

检测到的新型号只能成为**候选**，不能自动晋升。原因是：文档措辞可能变化；新模型不一定
对当前账号可用；产品语义默认模型变更还必须重新做 Stage 04 资格验证。唯一的晋升路径是
经过评审的 pull request。这样既能跟随官方资料，也不会破坏 Stage 03 profile 契约和
Stage 04 测量协议。

### 3.1 新鲜度与安全拒绝

内置 profile 包含 `captured_at`、`review_after`、资料 URL、内容摘要、已评审断言和
评审记录。超过 `review_after` 后，自动路由返回 `profile_stale`，不会继续声称推荐仍然
有效。`candidate`、未知、陈旧或不兼容 profile 都不能支持自动选择。

精确用户 pin 也不能绕过这些门禁。模型仍须针对目标能力完成资料评审，支持指定 effort，
并在真正调用前对账号可见。当前不提供隐式 fallback。未来若增加 fallback，必须证明是
同一能力的等价选择、由用户显式启用，并进入 selection digest。

## 4. 配置契约

默认策略是 `auto`；具体 model ID 存在 profile 数据里，而不是成为永久代码常量。
2026-08-17 已评审 profile 的当前值如下：

| 能力 | 当前文档默认值 | Effort | 当前用途 |
| --- | --- | --- | --- |
| `codex.advisory_review` | `gpt-5.6-sol` | `max` | 可选、只读的 PR review；不是产品证据 |
| `semantic.reasoning_quality_first` | `gpt-5.6-sol` | `max` | manifest 绑定的开发性 Codex Desktop 适配器；尚未资格验证 |
| `semantic.reasoning_balanced` | `gpt-5.6-terra` | `medium` | 用户明确选择的成本/质量档，不作隐式 fallback |
| `semantic.reasoning_high_volume` | `gpt-5.6-luna` | `medium` | 用户明确选择的高吞吐档，不作隐式 fallback |

当前 CLI 示例：

```sh
# 只解析默认选择，不调用 OpenAI。
agent-doctor model resolve \
  --capability semantic.reasoning_quality_first \
  --as-of 2026-08-17

# 用户精确 pin 型号和 effort；仍然不会发起提供商调用。
agent-doctor model resolve \
  --capability semantic.reasoning_balanced \
  --strategy pinned \
  --model gpt-5.6-terra \
  --reasoning-effort high \
  --available-model gpt-5.6-terra \
  --as-of 2026-08-17

# 要求产品语义资格门禁。由于尚未执行资格评测，当前会明确阻断。
agent-doctor model resolve \
  --capability semantic.reasoning_quality_first \
  --available-model gpt-5.6-sol \
  --require-qualified --require-ready \
  --as-of 2026-08-17
```

生产语义适配器最终采用以下持久配置优先级：

1. CLI 中的精确 model/effort；
2. 已独立确认可信的项目级 Agent Doctor 配置；
3. 用户级 Agent Doctor 配置；
4. 当前已评审 profile 的默认值。

只有独立确认项目可信时才读取项目级设置。每个解析后的字段都记录来源。持久 Agent
Doctor TOML 加载尚未实现；当前语义控制通过显式 CLI 选择和精确披露摘要完成。不可信
仓库文本不能授予调用授权，也不能触发提供商调用。

Codex advisory workflow 支持：

- `CODEX_REVIEW_MODEL`，默认等于已评审 profile 的型号；
- `CODEX_REVIEW_EFFORT`，默认等于已评审 profile 的 effort。

修改任一项都属于明确用户策略。自动测试会检查 workflow 默认值与 profile 一致。

## 5. 选择产物与失效规则

每次解析输出一份稳定 JSON，包含：

- 能力及 `auto`/`pinned` 策略；
- 精确 model 与 reasoning effort；
- 选择来源；
- profile ID、版本、采集日期、复核日期；
- 官方资料引用；
- 账号可用状态与传入可用集合的摘要；
- 资格状态、可归因的测量记录引用，以及本次是否强制资格；
- blockers、调用就绪状态、是否发生 fallback；
- decision ID 与 selection digest。

disclosure manifest、语义请求元数据、缓存键、可复现元数据和 provider 资格身份都包含
selection digest。model、effort、profile、能力、账号可用集合、adapter、prompt
契约、分类法、输入或政策任一变化，都会按 Stage 03–04 要求使相应 authorization/cache/
qualification 身份失效。

## 6. 生产语义管线设计

语义层只扩展现有确定性结果图，不取代本地脚本和证据。

### 6.1 有序流程

1. 先完成冻结范围、盘点、解析、引用/配置/优先级/适用性解析，以及所有相互独立的
   确定性检查；
2. 先按带版本的词法重合与语气冲突检索候选 Skill 对，再只对语义证据确实有价值的
   候选，按一个主张集合、一个区域、一个维度建立问题。检索分数只选择有界面板，绝不
   作为标签、严重度、置信度或关系存在的证据；同分时确定性地平衡来源；
3. 解析已评审且新鲜的模型选择。要进入发布资格路径，还必须验证账号可用并通过产品
   资格门禁；
4. 内容代理只取最小决定性摘录，排除原始凭证、检测到的秘密、脚本/可执行正文、无关
   文件、越界引用和未获批内容；
5. 构建披露清单，写明 provider、精确 model/effort、selection digest、adapter/prompt/
   taxonomy 版本、用途、内容句柄、排除项、保留/缓存事实和响应契约；
6. 独立调用时展示清单并要求确认精确 digest；用户显式发起一键语义运行时，先记录
   manifest，并只把该请求作为紧接着生成的 digest 的单次授权。两者都不授予写权限、
   可复用权限或后台权限；
7. 在两个彼此隔离的全新 ephemeral Codex 上下文中并行调用分析者 A/B。二者互相盲审，
   以正序/逆序查看同一来源，没有任意文件系统访问权，payload 与日志不含凭证，并逐一
   回答每个冻结的 Skill 对/维度问题。MVP 的单个三上下文 panel 最多发出 16 个问题；
   其余问题必须成为显式覆盖缺口，用户可精确缩小到 Skill 对来获得该对的完整覆盖。
   每个分析者还会收到紧凑身份表，其中来源、句柄、允许主张和维度都是封闭复制契约；
8. 两份分析结果都通过验证后，再在第三个全新上下文中调用仲裁者。它读取两份答案，
   搜索反例和缺失证据，并记录共识、已裁决分歧、挑战或证据不足；
9. 校验三次调用的生命周期、封闭 schema/标签/建议、问题/来源/维度的精确 join、内容
   句柄引用、秘密回显、来源顺序披露和请求/响应身份；非法或无引用面板输出不可使用。
   建议选择与 disposition 使用嵌套 schema 联合类型，使 `selected_from=none` 在结构上只能
   配对 `disposition=not_applicable`；结构合法但与标签不兼容的建议由本地丢弃，既不能使
   已独立校验的关系失效，也不能提升该关系；
10. 三个模型角色的陈述都只能作为不可变 `inferred` 证据；
11. 本地裁决器必须先确认双分析者共识、仲裁者确认、反例已关闭、没有缺失证据、建议与标签兼容，再负责
    适用性、分类法、状态、标签、限定符、严重度、置信度、去重和分组；共同适用区域
    未建立时，即使冲突或重复得到共识，也只能保留为 candidate；分析者分歧即使被仲裁，
    也最多形成 candidate，不能直接成为 finding 或 pass；
12. 最终仍封存一份供人类可读终端、Markdown、JSON 和 CI 共用的结果图。

### 6.2 提供商响应契约

两个分析者分别针对每个冻结问题返回候选关系、已披露句柄/主张引用、简短理由、共同区域
判断、各自贡献、反例状态、缺失证据，以及一个有边界的手工建议候选。仲裁者可以确认
共识、从两个分析标签中裁决分歧、挑战双方或声明证据不足。三个角色都不得设置产品检查
状态、严重度、最终置信度、权限、修复操作、范围或证据来源类型；即便三者一致，也不能
把模型意见升级为确定性证明，仲裁也不能隐藏原始分歧。

建议种类使用封闭词表。本地兼容表只能把已复核的候选变成
`authority=none`、`automatic_apply=false` 的下一步，并明确记录预期收益、风险与验证方法。
未知、被挑战、不兼容或未验证建议必须丢弃，或替换为通用证据请求。

被分析文件里的 prompt-like 文字只是不可信数据。它不能修改系统契约、增加内容句柄、
更换模型、请求其他工具、授权操作或改变保留策略。

### 6.3 失败语义

| 生命周期位置 | 必须行为 |
| --- | --- |
| 语义模式关闭 | 相关检查为 `not_run`，确定性结果继续可用 |
| 开始前没有已评审/新鲜/可用/合格路线 | `not_run`，准确记录能力缺口 |
| 缺决定性的已批准内容 | `insufficient_evidence`，不启动 provider |
| 独立调用摘要不存在或不匹配 | `not_run`，provider 请求数为零 |
| 请求开始后超时或传输失败 | 对应检查为 `error`，已有结果保留 |
| 响应畸形、无引用、回显秘密或越权 | 响应不可用；产生 `error` 或安全脱敏事件 |
| 已完成证据仍然含糊 | 本地 `insufficient_evidence` 或有边界 `candidate`，不能强判 finding |
| 静态证据只支持运行时选择假设 | `candidate` + `runtime_validation_needed`，不能声称运行结果 |

跨运行语义响应缓存继续关闭。未来 opt-in 缓存必须保存在本地、披露保留策略，并包含第 6
节所有身份字段。

## 7. 可评审垂直切片

| 切片 | 产物 | 进入条件 | 完成条件 | 当前状态 |
| --- | --- | --- | --- | --- |
| 06-A | 已评审模型 profile、离线路由、官方资料 watcher、用户覆盖、MR suite | Stage 01–05 契约 | 所有保留 MR 场景通过；无隐式晋升/fallback | 已在工作树实现 |
| 06-B | 生产 disclosure manifest 与逐次精确授权 | 06-A | 秘密/脚本排除、摘要失效、错摘要零调用测试通过 | 本地已实现 |
| 06-C | 并行盲审分析者 + 仲裁者 Codex Desktop 面板、schema/引用/建议校验、本地裁决桥、人类输出与封存图接入 | 06-B | 并行、盲审、仲裁顺序/身份、分歧降级、权限/引用门禁、人类输出与封存图测试通过 | 已实现，未资格验证 |
| 06-D | 开发语料、独立 holdout、真实合成 canary、model/effort 对比 | 06-C | Stage 04 样本充分、绝对隐私门禁、三次独立真实运行 | 受语料/评审资源阻塞 |
| 06-E | 本地 baseline/delta 与私有定时运行 | 稳定封存语义图 | 增量可复现、导出脱敏、不自动修复 | 规划中 |

自动修复仍不在范围内。语义 finding 只能进入现有 proposal/manual 路径；Stage 04 完整
修复矩阵通过前不得自动 apply。

## 8. 可执行测试方案

### 8.1 模型路由契约

`test-spec/scenarios/stage-06-model-routing-v0.1.json` 由
`test-spec/schema/model-routing-suite.schema.json` 校验，运行命令为：

```sh
agent-doctor model spec --summary
```

保留的十一个 MR 场景覆盖：

- 已评审质量优先默认值与 max effort；
- 账号可用性不能成为排名；
- 精确用户 pin 与禁止静默替换；
- 未评审 pin、auto/pin 混用、陈旧 profile 的拒绝；
- 产品语义必须资格验证，而 advisory review 不冒充产品资格；
- Sol/Terra/Luna 三种明确能力档；
- 默认模型不可用时不 fallback。

代码级测试还覆盖资料域名 allowlist、profile 校验、selection digest 失效、只生成候选而
不晋升、资料抓取失败属于执行失败，以及 workflow/profile 默认值一致。

### 8.2 语义契约与集成测试

Stage 04 S-SEM-001–S-SEM-018 已在不修改原 oracle 的前提下可执行。普通 CI 只使用本地
契约替身和合成秘密哨兵，不发送真实请求，也不需要 API key。这些是规范回归检查，不是
独立测量语料。

集成层至少断言：

- 一个披露句柄不能泄漏另一来源；
- model/effort/profile/provider/content/purpose 变化使授权失效；
- 每个被接受引用都指向已披露句柄及精确版本；
- 在请求、日志、报告、指纹、缓存和失败包中都检查秘密/脚本排除；
- 拒绝模型返回的 state/severity/authorization；
- 分析者角色/身份不一致、缺少仲裁、关联错误或仲裁引用缺失必须被拒绝；
- 测试必须证明两个盲审分析者在时间上真实重叠，且仲裁者只在二者验证后启动；
- 分析者分歧必须可见并降级，不能用多数票掩盖；
- 分析者 B 必须逆序读取来源，prompt injection 文字始终只是被引用的数据；
- 建议种类及其与标签的兼容性由本地规则限制；
- 本地裁决保留全部模型证据为 `inferred`；
- provider 失败不删除确定性案例，并产生正确的局部运行结果；
- 四种输出仍然只是同一封存图的投影。

当前扩展 Stage 04 catalog 有 101 个场景可执行；其余 31 个修复写入/并发场景继续显式标为
不支持。这个数字只描述契约 runner 状态，不代表准确率、有用性、校准或发布就绪。

### 8.3 真实资格测试

真实测试只允许手动或在受保护环境运行，只使用合成内容，且必须有精确 disclosure
manifest；绝不在不可信 PR 上运行。记录 provider、model、effort、selection/profile
摘要、adapter、prompt 契约、taxonomy、输入摘要、重试和安全 request ID，绝不记录凭证。

晋升默认模型必须同时具备：

1. 可归因的官方推荐与能力证据；
2. 账号可用 canary；
3. 全部绝对语义/隐私/可复现门禁；
4. Stage 04 独立 holdout 与最低样本量；
5. 与现有默认值在质量、稳定性、延迟和成本上的对比；
6. 同一个 PR 中经过评审的 profile 与 workflow 变更。

上述测量实际产生前，不得声称准确率、有用性、校准或发布就绪。

## 9. CI/CD 运行方式

- 每个 PR 在无网络、无凭证条件下运行确定性测试、Stage 04 契约和模型路由 suite；
- 可选 Codex review 保持 advisory/read-only，使用仓库 variables 与 `OPENAI_API_KEY`
  单独配置；
- 每周 model-profile watcher 只访问公开官方资料，无 API key，也不能修改仓库；
- 未来真实语义 canary 必须位于受保护的手动 workflow，使用合成 fixture、环境级 secret、
  approval、费用/时间限制和脱敏产物；它不是确定性正确性门禁；
- profile 晋升、prompt 变化和资格变化都必须经过 PR，并使旧资格身份失效。

## 10. 约束性安全决定

1. 官方资料提名候选，测试和评审负责晋升默认值；
2. `/v1/models` 只证明可用性，绝不证明能力排名；
3. 默认策略为 `auto`，具体 ID 是可替换 profile 数据；
4. 用户 pin 必须精确、失败关闭，不静默换模型或降 effort；
5. Advisory review 与产品语义证据属于不同信任路径；
6. 产品语义调用必须具备精确披露授权、最小化、适配器校验、推断来源、本地裁决和资格验证；
7. 含义含混或明显离题的请求必须先确认，不能据此改变产品范围；
8. 静态 Skill 证据仍不能证明运行时选择或因果；
9. 修复继续保持 proposal/manual-only。
