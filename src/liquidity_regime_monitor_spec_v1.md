# 流动性体制月度监测系统 — 设计规格 v1.0

> 代号:LRM (Liquidity Regime Monitor)
> 用途:本文档交给 Claude Code 作为实施蓝图。所有阈值、权重均为**事前默认值**,使用者(Shawn)在 config 中修改后即冻结,运行期内不得随行情调整。

---

## 0. 系统定位与非目标

**定位**:月度运行的体制分类器(regime conditioner)。读取四层流动性数据 + 央行文本,输出当前所处象限、主动仓位水位上限、杠杆规则,以及日度中断警报。它回答的问题是:**"当前环境下,风险该开多大?"**

**非目标(写死,防止范围蔓延)**:
- 不输出任何买卖指令、标的选择、进出场点位。
- 不做日度方向判断(那是波动率系统的领域)。
- 不预测拐点,只对已发生的状态变化做规则化反应。
- 不替代脆弱性预警系统,只为其提供象限乘数。

**系统拓扑(三件套)**:
```
流动性体制系统(月度) ──象限/水位──▶ 共享状态存储(JSON)
                                        │
脆弱性预警系统(已有) ◀──象限乘数────────┤
波动率监测系统(规划中,日度) ◀──象限上下文─┘
                └──vol_regime flag──▶ LRM 日度中断模块(作为输入之一)
```

---

## 1. 设计原则(架构级约束,实施时不得违反)

1. **机械状态机 + 顾问型 LLM**。象限判定完全由数据和事前规则产出。LLM 只做文本分析(FOMC diff、反应函数定性)和月度综述,可在 `analyst_dissent` 字段表达异议,**无权修改象限字段**。
2. **Vintage 纪律**。每条数据入库时记录 `(value, observation_date, as_of_date)` 三元组。任何回测/复盘只允许使用 `as_of_date ≤ 回测时点` 的数据。月度报告标注每条输入的数据陈旧度。
3. **简约与封权**。指标总数 ≤ 25 条核心序列。每条指标必须在复合公式中有明确角色,否则删除。"净流动性"权重封顶 0.20,防止系统退化为万能事后解释。
4. **权重为先验,禁止寻优**。复合权重是判断给出的先验,每年人工审议一次。可做敏感性分析(±50% 权重扰动下象限是否稳定),**禁止用历史收益优化权重**。
5. **影子运行**。上线后前 6 个月只记录、不约束实盘。期满后用第 10 节的评估协议决定是否接入真实水位管理。

---

## 2. 架构总览

```
┌─ 数据层(daily/weekly cron)
│   fetchers/* → SQLite(vintage 三元组)→ 数据质量检查
│
├─ 计算层(月度运行,默认每月最后一个周六)
│   transforms(Δ、z-score、percentile)→ composites(L、R 分数)
│   → regime(状态机 + 迟滞)→ 象限 + 水位
│
├─ LLM 层(月度;FOMC 月加跑会后专项)
│   fomc_diff / reaction_function / boj_pboc_scan / monthly_synthesis
│
├─ 中断层(daily cron,轻量)
│   alerts:管道、信用、外汇、carry 背离、加密风偏、央行突发
│
└─ 输出层
    月报(Markdown/HTML)+ 状态卡 JSON(写入共享存储)+ 即时通知(Telegram/邮件)
```

**运行日历**:
- 日度:数据抓取 + 中断检查(北京时间每日早 07:00,覆盖美东收盘后数据)。
- 周度:H.4.1(周四美东发布)入库后更新管道层面板。
- 月度主运行:每月最后一个周六。此时已可得:当月社融(~15日)、上月保证金债务(~第3周)、当月 FOMC(若有)。
- 事件驱动:FOMC/BoJ/PBoC 政策日的次日跑 LLM 专项模块。

---

## 3. 指标清单(四层)

> 表格列说明:**变换** 中 Δ3m 对日度序列 = 63 个交易日差分,对周度 = 13 周;z = 滚动 5 年 z-score(日度 1260 个观测/周度 260 个,最少 3 年否则用全样本),截断于 ±2;符号已调整为 **正值 = 流动性扩张 / 风险偏好上升**。

### 3.1 第一层:货币价格(Price of Money)

| 指标 | 序列/来源 | 频率 | 发布滞后 | 变换 | 角色与权重 |
|---|---|---|---|---|---|
| 10Y TIPS 实际利率 | FRED `DFII10` | 日 | T+1 | level, −Δ3m z | **L 复合 0.25**(核心,科技股估值锚) |
| 2Y 国债收益率 | FRED `DGS2` | 日 | T+1 | level, Δ3m | 上下文(政策预期摘要) |
| 收益率曲线 2s10s / 3m10s | FRED `T10Y2Y` / `T10Y3M` | 日 | T+1 | level, Δ3m | 上下文,不进复合 |
| 5y5y 通胀预期 | FRED `T5YIFR` | 日 | T+1 | level | 拆解实际 vs 名义驱动,上下文 |
| 市场隐含路径 vs 点阵图 | CME FedWatch(抓取)+ `config/dots.yaml`(季度手动维护) | 日/季 | — | 12 个月期隐含利率 − 同期限点阵中位数,单位 bp | **L 复合 0.10**(−Δ1m 方向项);**水平值单列于报告头版**,是重定价风险的方向指针 |
| ACM 期限溢价(可选) | NY Fed ACM 日度 CSV(`ACMTP10`) | 日 | T+1 | Δ3m | 上下文,久期重定价通道 |

FedWatch 抓取失败时的降级代理:`DGS2 − EFFR`(FRED `EFFR`)的 Δ1m,并在报告中标注代理状态。

### 3.2 第二层:数量与管道(Plumbing)

| 指标 | 序列/来源 | 频率 | 发布滞后 | 变换 | 角色与权重 |
|---|---|---|---|---|---|
| 联储总资产 | FRED `WALCL` | 周(三) | 周四发布 | Δ13w | 净流动性组件 |
| 准备金余额 | FRED `WRESBAL` | 周 | 周四 | Δ13w z;**Reserves/GDP 比率** | **L 复合 0.10**;比率进警戒线监控 |
| ON RRP | FRED `RRPONTSYD` | 日 | T+1 | level, Δ13w | 净流动性组件 |
| TGA | FRED `WTREGEN`(周)+ Treasury FiscalData API 日度现金余额 | 周/日 | T+1 | Δ13w | 净流动性组件 |
| **净流动性** = WALCL − TGA − RRP | 派生 | 周 | — | Δ13w z | **L 复合 0.20(封顶)**。报告中固定标注:"诊断指标,非定律" |
| SOFR − IORB 利差 | FRED `SOFR` − `IORB` | 日 | T+1 | level,连续为正天数 | 不进复合;**中断规则源**(管道压力) |
| SRF 用量 | NY Fed 公开数据 | 日 | T+1 | 非季末用量 | 中断规则源 |
| 贴现窗口主信贷 | FRED `WLCFLPCL` | 周 | 周四 | 周增 z | 中断规则源(银行压力) |
| Reserves/GDP | `WRESBAL` / 名义 GDP(FRED `GDP` 季度,线性内插) | 周 | — | 比率水平 | 警戒线:**黄 < 10%,红 < 9%**(config 可调;历史校准点:2019 年 9 月回购危机发生在 ~7%) |

### 3.3 第三层:私人风险承担(Private Risk-Taking)

| 指标 | 序列/来源 | 频率 | 发布滞后 | 变换 | 角色与权重 |
|---|---|---|---|---|---|
| 高收益债 OAS | FRED `BAMLH0A0HYM2` | 日 | T+1 | −Δ3m z;10 年分位 | **R 复合 0.35**(核心);中断规则源 |
| 投资级 OAS | FRED `BAMLC0A0CM` | 日 | T+1 | level | 上下文(质量轮动) |
| CCC−BB 利差 | FRED `BAMLH0A3HYC` − `BAMLH0A1HYBB` | 日 | T+1 | −Δ3m z | **R 复合 0.10**(垃圾级深度的风偏温度) |
| FINRA 保证金债务 | FINRA 月度统计页(抓取) | 月 | **~3–4 周** | Δ YoY z(最新 vintage) | **R 复合 0.15**;陈旧度预算 6 周,超期降权重并重归一化 |
| 稳定币总市值 | DefiLlama API `stablecoins.llama.fi` | 日 | 实时 | Δ1m z | **R 复合 0.15**(全球风偏前哨,反应快于股票);中断规则源 |
| BTC 资金费率 + 总未平仓 | 交易所直连(Binance/OKX/Bybit 公开 API 聚合);备选 Coinglass(~$30/月) | 日 | 实时 | 上下文面板 | 不进复合(避免与稳定币重复计量);供脆弱性系统交叉引用 |
| IPO 窗口 | Renaissance IPO ETF(`IPO`)3 个月相对 SPY(yfinance 免费) | 日 | T+1 | 3m 相对收益 z | **R 复合 0.10**(发行市场冷热的系统化代理) |
| SLOOS C&I 信贷标准 | FRED `DRTSCILM` | 季 | ~1 个月 | level | 慢变量上下文,不进复合 |

### 3.4 第四层:全球(Global)

| 指标 | 序列/来源 | 频率 | 发布滞后 | 变换 | 角色与权重 |
|---|---|---|---|---|---|
| 广义美元指数 | FRED `DTWEXBGS` | 日 | T+1 | −Δ3m z | **L 复合 0.15**(美元升 = 全球收紧) |
| USD/JPY | FRED `DEXJPUS` | 日 | T+1 | Δ1m/Δ3m | 中断规则源(套息资金端);与 BoJ 模块联读 |
| 10Y JGB 收益率 | 日本财务省日度 CSV(免费) | 日 | T+1 | 周变动 | 中断规则源 |
| **AUD/JPY** | 派生:`DEXUSAL × DEXJPUS` | 日 | T+1 | Δ3m z;**与 NDX 3m 趋势的背离** | **R 复合 0.15**;独立背离中断规则(见第 6 节)。失真说明写入报告模板:BoJ 政策重定价期、AUD 特异性冲击期需联读 JGB/BoJ 模块 |
| USD/CNY | FRED `DEXCHUS` | 日 | T+1 | Δ1m | 上下文(资本流/政策信号,关联中国资产敞口) |
| 中国信贷脉冲 | AKShare 社融增量(`macro_china_shrzgm`,函数名实施时核验)+ GDP | 月 | ~15 日 | (社融 12m 滚动和 / 名义GDP) 的 Δ3m z | **L 复合 0.10**;陈旧度预算 6 周 |
| 中国 M1−M2 剪刀差 | AKShare 货币供应 | 月 | ~15 日 | level, Δ | 上下文(中国本土流动性偏好) |
| PBoC 政策利率(7 天 OMO / MLF / LPR) | AKShare + LLM 月度扫描 | 不定期 | — | 事件 | LLM 模块输入 |
| 全球央行资产负债表复合 | `WALCL` + `ECBASSETSW` + `JPNASSETS`(+ PBoC 总资产,AKShare) | 周/月 | — | **各 CB 本币 3m 增速,按美元规模加权平均**(避免汇率折算与美元指数重复计量) | **L 复合 0.10** |
| BoJ 政策声明 | BoJ 官网(年 8 次会议) | 事件 | — | 文本 | LLM 模块输入 |

**L 复合权重合计**:0.25 + 0.20 + 0.10 + 0.15 + 0.10 + 0.10 + 0.10 = **1.00**
**R 复合权重合计**:0.35 + 0.15 + 0.15 + 0.15 + 0.10 + 0.10 = **1.00**

**数据质量规则**:日度序列允许前向填充 ≤ 5 个交易日;月度序列禁止跨发布期填充;任一复合成分超过陈旧度预算时,从复合中剔除该成分、剩余权重重归一化,并在报告与日志中显式警告。

---

## 4. 复合指标与状态机

### 4.1 复合分数

对每个成分 i:`x_i = clip( z_5y( signed_transform_i ), −2, +2 )`,符号统一为正值 = 扩张/风偏上升。

```
L = 0.25·x(−Δ3m DFII10) + 0.20·x(Δ13w NetLiq) + 0.10·x(Δ13w WRESBAL)
  + 0.15·x(−Δ3m DTWEXBGS) + 0.10·x(Δ3m GlobalCB_localFX) 
  + 0.10·x(Δ3m ChinaCreditImpulse) + 0.10·x(−Δ1m ImpliedPath12m)

R = 0.35·x(−Δ3m HY_OAS) + 0.15·x(Δ1m StablecoinMcap) + 0.15·x(Δ3m AUDJPY)
  + 0.15·x(Δ MarginDebt_YoY) + 0.10·x(IPO_ETF_rel3m) + 0.10·x(−Δ3m CCC_BB_spread)
```

L、R ∈ [−2, +2]。

### 4.2 状态机(迟滞规则)

方向判定:
- 原始方向:score ≥ +0.25 → 扩张/上升;≤ −0.25 → 收缩/下降;中间带 → **保持上月状态**。
- 状态翻转确认(满足其一):
  - (a) 当月 |score| ≥ 0.50(单月强确认);
  - (b) 连续两个月同号且 |score| ≥ 0.25(双月确认)。
- 紧急降级:月内触发"管道红"或"信用红"中断(见第 6 节)时,可临时下调一个象限(Q1→Q2/Q3,Q2/Q3→Q4),标记 `provisional=true`,下次月度主运行时复核转正或撤销。临时降级需人工确认后生效——系统建议,人按按钮。

### 4.3 象限定义与水位(默认值 = 占位符,使用者在 config 冻结前修改)

| 象限 | 条件 | 主动仓位上限 | 杠杆 | 配套规则 |
|---|---|---|---|---|
| **Q1 顺风** | L↑ R↑ | ≤ 15%(满额) | ≤ 1.2× | 脆弱性警报为建议性 |
| **Q2 托底回撤** | L↑ R↓ | ≤ 10% | 1.0× | 历史上偏命题交易的加仓窗口(流动性托底、风偏回撤)——写为提示,不写为指令;脆弱性警报为约束性 |
| **Q3 余热** | L↓ R↑ | ≤ 10% | 1.0× | **6/5 原型象限**:靠惯性运转、燃料在抽走。脆弱性系统警报权重 ×1.5;趋势仓止损收紧一档 |
| **Q4 双杀** | L↓ R↓ | ≤ 5% | 1.0× | 禁开新价格交易;命题交易只按事前写明的价位执行 |

水位约束的对象是 **15% 主动卫星仓**,核心 85% 被动仓不受本系统管辖。

---

## 5. LLM 反应函数模块

模型:Claude API,低 temperature,强制 JSON 输出(schema 校验,失败重试一次后降级为人工待办)。月度批处理,FOMC/BoJ 会议次日加跑专项。所有 prompt 注入同一条**护栏指令**:

> 你是数据分析师,不是决策者。你不得输出任何买卖建议,不得修改 quadrant 字段。如你的定性判断与机械状态机输出冲突,将异议写入 analyst_dissent 字段,陈述证据,不下指令。

### 5.1 任务 P1:FOMC 声明 diff

输入:本次声明全文 + 上次声明全文(federalreserve.gov,公开文本)。
输出 schema:
```json
{
  "changes": [{"old": "...", "new": "...", "classification": "hawkish|dovish|neutral",
               "mandate_variable": "inflation|employment|financial_stability|other"}],
  "hawk_dove_score": -5..+5,
  "financial_conditions_mention_count": int,
  "summary_zh": "≤120字"
}
```

### 5.2 任务 P2:反应函数状态判定

输入:最新声明 + 会议纪要节选 + 近 30 天 3 篇关键官员讲话(联储官网 RSS 抓取,主席与理事优先)+ 数据层算出的 `fed_vs_market_gap_bps`。
输出 schema:
```json
{
  "status": "stable | revision_watch | rewriting",
  "dominant_variable": "inflation | employment | financial_stability | balanced",
  "evidence": ["引用来源与关键句,每条≤30字"],
  "gap_convergence_view": "market_moves_to_fed | fed_moves_to_market | unclear",
  "confidence": 0.0-1.0
}
```
判定参考(写入 prompt):新框架语言出现、异议票模式变化、非常规变量进入声明、计划外行动 → 向 `rewriting` 倾斜。**status 字段是整份月报的头条**:函数稳定期,盈利通道主导,个股分化;函数改写期,流动性通道压倒一切,相关性趋一。

### 5.3 任务 P3:BoJ / PBoC 扫描(季度或事件触发)

BoJ:声明 + 行长记者会要点 → `{policy_shift: bool, carry_implication: "tightening|easing|neutral", note_zh}`。
PBoC:货币政策执行报告(季度)+ 利率/准备金率变动 → `{stance_shift, credit_impulse_outlook, note_zh}`。

### 5.4 任务 P4:月度综述

输入:全部指标 JSON + P1–P3 输出 + 上月状态卡。
输出:≤600 字中文备忘录,固定结构:① 本月象限与变化;② 四层各自最重要的一个变化;③ **证伪清单**(下月哪些数据组合会推翻当前象限);④ 已武装的中断触发器;⑤ `analyst_dissent`(可选)。

---

## 6. 日度中断规则(alerts.py)

| # | 触发条件 | 等级 | 动作 |
|---|---|---|---|
| 1 | SOFR > IORB 连续 ≥ 3 个交易日(剔除季末 ±2 日) | 管道黄 | 通知 + 标记 |
| 2 | SOFR − IORB 单日 ≥ +10bp(非季末) | **管道红** | 通知 + 临时降象限建议 |
| 3 | SRF 非季末用量 > 0 | 管道黄 | 通知 |
| 4 | 贴现窗口主信贷周增 > 2σ(5 年窗口) | 银行压力 | 通知 |
| 5 | HY OAS 10 个交易日走阔 ≥ +50bp | **信用红** | 通知 + 临时降象限建议 |
| 6 | HY OAS 10 个交易日走阔 ≥ +25bp | 信用黄 | 通知 |
| 7 | DTWEXBGS 5 日升 ≥ +2.5% | 美元冲击 | 通知 |
| 8 | USD/JPY 5 日变动 ≥ ±3% 或 10Y JGB 周变动 ≥ 25bp | 套息资金端 | 通知 + 触发 P3-BoJ 扫描 |
| 9 | **AUD/JPY 10 日跌 ≥ 4% 且 NDX 同期 ≥ 0** | carry 背离 | 通知(隐性解杠杆前哨) |
| 10 | 稳定币总市值 7 日缩水 ≥ 3% | 加密风偏 | 通知;抄送脆弱性系统 |
| 11 | 计划外央行公告(RSS 关键词 + LLM 日扫一次) | 事件 | 触发对应 LLM 专项 |
| 12 | (预留)波动率系统 `vol_regime` 翻转为 stress | 跨系统 | 中断检查频率提升至日内 |

红色中断 → 生成 off-cycle 迷你报告(指标快照 + LLM 一段话定性)+ 临时降象限建议,等待人工确认。


---

## 7. 输出规格

### 7.1 月报模板(Markdown,自动渲染 HTML)

```
1. 状态卡头版:象限(含上月对比)、L/R 分数、水位指令、反应函数 status、
   fed_vs_market_gap_bps、本月触发过的中断
2. 第一层面板:实际利率走势图、隐含路径 vs 点阵图
3. 第二层面板:净流动性分解堆叠图、Reserves/GDP 距警戒线、SOFR-IORB
4. 第三层面板:HY OAS 与分位、稳定币市值、保证金债务(标注 vintage)、IPO 窗口
5. 第四层面板:美元指数、AUD/JPY 与 NDX 背离图、中国信贷脉冲、全球 CB 复合
6. LLM 综述(P4 输出)
7. 附录:数据陈旧度表、本月数据质量警告、被剔除并重归一化的成分
```

### 7.2 状态卡 JSON 契约(写入共享存储,供三系统互读)

```json
{
  "system": "LRM",
  "version": "1.0",
  "as_of": "2026-06-27",
  "run_id": "lrm-2026-06",
  "quadrant": "Q3",
  "quadrant_provisional": false,
  "L_score": -0.42,
  "R_score": 0.31,
  "water_level": {"active_sleeve_max_pct": 10, "leverage_max": 1.0,
                  "fragility_alert_multiplier": 1.5},
  "reaction_function": {"status": "revision_watch",
                        "dominant_variable": "inflation",
                        "fed_vs_market_gap_bps_12m": -38},
  "alerts_active": ["carry_divergence"],
  "data_vintages": {"margin_debt": "2026-05-31/as_of 2026-06-24",
                    "china_tsf": "2026-05/as_of 2026-06-15"},
  "analyst_dissent": null
}
```

接口约定:脆弱性系统读 `quadrant` 与 `fragility_alert_multiplier`;波动率系统(建成后)读 `quadrant` 作上下文,并写回 `vol_regime` 供中断 #12 消费。

---

## 8. 数据源采购与成本清单

| 来源 | 覆盖 | 成本 | 稳定性 |
|---|---|---|---|
| FRED API(免费 key) | 第 1/2/3/4 层约 70% 序列 | $0 | 高 |
| Treasury FiscalData API | TGA 日度 | $0 | 高 |
| NY Fed 公开数据 | SRF、ACM 期限溢价 | $0 | 高 |
| 日本财务省 | JGB 日度收益率 CSV | $0 | 高 |
| FINRA 统计页 | 保证金债务 | $0 | 中(页面改版风险,做解析失败告警) |
| DefiLlama API | 稳定币市值 | $0 | 中高 |
| 交易所公开 API(Binance/OKX/Bybit) | 资金费率、OI | $0 | 中高 |
| AKShare(开源库) | 社融、M1/M2、LPR、PBoC 资产 | $0 | 中(接口随源站变动,实施时核验函数名,做降级路径) |
| CME FedWatch(页面抓取) | 隐含政策路径 | $0 | **低**(必须实现 `DGS2−EFFR` 降级代理) |
| yfinance | IPO ETF、NDX | $0 | 中 |
| 央行官网 + RSS | FOMC/BoJ/PBoC 文本 | $0 | 高 |
| Coinglass(可选) | 聚合资金费率/OI/清算 | ~$30/月 | 高 |
| Claude API | LLM 模块,月度批处理 | < $5/月 | 高 |

**总成本:$0–35/月。** 原则:每个关键输入必须有免费主源 + 降级路径;预算优先留给波动率系统的数据采购。

---

## 9. 实施路线图(交 Claude Code 执行)

### 9.1 仓库结构

```
liquidity-monitor/
├── config/
│   ├── indicators.yaml      # 序列、来源、变换、权重、符号、陈旧度预算
│   ├── thresholds.yaml      # 状态机阈值、迟滞、水位表、中断规则
│   ├── dots.yaml            # 点阵图中位数(季度手动更新,5分钟任务)
│   └── secrets.env          # API keys(不入版本库)
├── src/
│   ├── fetchers/            # fred.py treasury.py nyfed.py mof_jp.py finra.py
│   │                        # defillama.py exchanges.py akshare_cn.py
│   │                        # fedwatch.py(含降级代理) yf.py cb_texts.py
│   ├── store.py             # SQLite,vintage 三元组读写
│   ├── quality.py           # 填充规则、陈旧度、解析失败告警
│   ├── transforms.py        # Δ、滚动 z、分位、截断
│   ├── composites.py        # L/R 计算 + 成分剔除重归一化
│   ├── regime.py            # 状态机、迟滞、临时降级、状态历史
│   ├── llm/
│   │   ├── prompts/         # p1_fomc_diff.md p2_reaction_fn.md p3_boj_pboc.md p4_synthesis.md
│   │   └── runner.py        # schema 校验、重试、降级为人工待办
│   ├── alerts.py            # 日度中断引擎(规则表驱动)
│   ├── report.py            # 月报渲染 + 状态卡 JSON
│   └── notify.py            # Telegram/邮件
├── data/                    # SQLite + 报告归档
├── tests/                   # 每个 fetcher 的快照测试;状态机单元测试(迟滞边界用例)
└── run_monthly.py / run_daily.py
```

### 9.2 分阶段

| 阶段 | 内容 | 验收标准 |
|---|---|---|
| P1 数据层 | 全部 fetchers + vintage 存储 + 质量检查;回填 10 年历史 | 25 条序列每日自动更新,vintage 字段完整,任一抓取失败有告警 |
| P2 复合与状态机 | transforms/composites/regime + 无 LLM 月报 | 用回填数据生成过去 24 个月的逐月象限序列(注意:回填期的月度序列 vintage 不完整,此序列仅作合理性检查,不作回测证据) |
| P3 LLM 模块 | P1–P4 任务接入,月报完整版 | FOMC 月跑通全链路;schema 校验通过率 100%(含重试) |
| P4 中断层 | alerts.py + 通知 | 用历史数据重放 2024-08(BoJ 冲击)与 2026-06-05 前后窗口,确认规则 #5/#8/#9/#10 按预期触发 |
| P5 影子运行 | 6 个月,只记录不执行 | 每月按第 10 节协议记录;期满出评估报告,人工决定是否接入实盘水位 |

---

## 10. 已知陷阱与验证计划

**陷阱清单(实施与使用时主动防御)**:
1. **未来函数**:回填历史的月度序列(保证金债务、社融)无法重建真实 as_of,P2 的历史象限序列只能当合理性检查。真正的证据从影子运行第 1 个月开始积累。
2. **净流动性叙事化**:该指标 2021–2023 拟合优美、随后多次失灵。权重已封顶 0.20,报告固定标注,禁止因"最近很准"上调权重。
3. **阈值幻觉**:±0.25/±0.50 与水位表都是先验占位,影子期结束前不具有证据地位。
4. **抓取脆弱性**:FedWatch、FINRA、AKShare 三处必须有降级路径与解析告警,否则系统静默退化。
5. **范围蔓延**:任何"顺便加个买卖信号"的冲动 → 拒绝,引用第 0 节非目标。

**影子期评估协议(每月记录,6 个月后汇总)**:
- 记录:当月象限、L/R、水位指令、中断触发;之后 1 个月与 3 个月的 NDX/SPX 收益与最大回撤;脆弱性系统警报与象限的同期关系。
- 评估问题:**不是"象限预测了涨跌吗"**,而是 ① 若按水位执行,主动仓的回撤分布是否改善;② Q3/Q4 象限是否在统计上对应更差的左尾;③ 中断规则的误报/漏报比是否可接受(每条规则单独记账)。
- 敏感性:权重 ±50% 扰动下,历史象限翻转的月份占比 < 20% 视为结构稳健。
- 决策:三问中至少两问为"是" → 接入实盘水位;否则延长影子期或修订后重置计时。

---

## 附录:config 骨架示例

```yaml
# thresholds.yaml(节选)
state_machine:
  neutral_band: 0.25
  strong_confirm: 0.50
  two_month_confirm: 0.25
  emergency_downgrade_requires_human: true
water_levels:        # 占位默认,冻结前由使用者修改
  Q1: {sleeve_max_pct: 15, leverage_max: 1.2, fragility_mult: 1.0}
  Q2: {sleeve_max_pct: 10, leverage_max: 1.0, fragility_mult: 1.0}
  Q3: {sleeve_max_pct: 10, leverage_max: 1.0, fragility_mult: 1.5}
  Q4: {sleeve_max_pct: 5,  leverage_max: 1.0, fragility_mult: 1.5}
plumbing:
  reserves_gdp_yellow: 0.10
  reserves_gdp_red: 0.09
staleness_budget_weeks: {margin_debt: 6, china_tsf: 6}
review_cadence: {weights: annual, thresholds: post_shadow}
```

— 规格结束。实施顺序按 9.2;所有默认值在 P1 开始前由使用者审定一次并冻结。
