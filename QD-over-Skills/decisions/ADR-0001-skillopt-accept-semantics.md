# ADR-0001 — SkillOpt 的 accept 语义与 K=1 档案映射

- 状态: Accepted
- 日期: 2026-06-05
- 关联: T001（K=1 回归测试）；SPEC 命题 3.6；BRIEF §4 红线第 2 条；成功判据 C0；后续 T005。
- 依据: 直接读 `SkillOpt/` 源码(非转述),下列均带 `file:line`。

## 背景
T001 要求 QD 档案在 $K=1$ 时与 SkillOpt **逐决策等价**。必须先从真实代码确认 SkillOpt 的 accept 规则、`current`/`best` 追踪、slow-update 候选如何过 gate、受保护字段如何不被 step edit 覆盖。**不凭转述。**

## 确认的语义(源码)

### 1. 每步 gate = 纯函数 `evaluate_gate`(`skillopt/evaluation/gate.py:76-148`)
比较量 `cand = select_gate_score(hard, soft, metric, w)`(metric∈{hard,soft,mixed},默认 hard→取 hard)。判定:
- `cand > current_score`:
  - 且 `cand > best_score` → **accept_new_best**:current=best=candidate,best_score=cand,best_step=global_step。
  - 否则 → **accept**:current=candidate(current_score=cand);best 不变。
- 否则(`cand <= current_score`) → **reject**:current/best 全不变。

**严格 `>`,平局(cand==current)拒。比较对象是 `current`,不是 `best`。**

### 2. 状态写回(`trainer.py:1357-1366`)
trainer 把 `gate.current_*/best_*` 原样赋回;`accept|accept_new_best` 置 `current_origin=step_N`;`accept_new_best` 置 `best_origin`。

### 3. `current==best` 是 step 循环的不变量(关键)
baseline 把 `current_score=best_score`、`current_skill=best_skill` 设为相等(`trainer.py:830-836, 900-921`)。从相等态出发,step gate 只会走 **accept_new_best**(cand>current 即 cand>best)或 **reject**,**永不触发裸 `accept` 分支** → current 与 best 在 step 循环中**恒等**(分数与文本)。
→ 推论:SearchQA 那轮的「4 accept」实为 4 次 **accept_new_best**。

### 4. current/best 何时分叉?只在 epoch 级 slow-update
- **epoch-1 占位注入**(`trainer.py:1524-1538`):`inject_empty_slow_update_field(current_skill)` 给 current 文本加空的受保护字段,`best_skill` 变量**不动** → 文本上 current≠best,分数仍相等。
- **force-accept 模式(默认,`slow_update_gate_with_selection=False`)**(`trainer.py:1749-1768`):slow guidance 用 `replace_slow_update_field` **无条件**注入 current 与 best **两者**,**不改分数**。
- **gated 模式**(`trainer.py:1665-1748`):slow 候选在 selection 集评分后走**同一个 `evaluate_gate`**;可产生 accept/accept_new_best/reject(此时才可能 current<best)。
→ 唯一能让 current/best 真正分叉、或触发裸 `accept` 的来源是 **epoch 级 slow-update**;**per-step 选择逻辑里二者恒等**。

### 5. 受保护 slow-update 字段(`slow_update.py:29-88` + `optimizer/skill.py:14-125`)
- 标记 `<!-- SLOW_UPDATE_START/END -->`;`replace_slow_update_field` 先删所有旧区再追加唯一新块。
- **step edit 不可碰保护区**(`skill.py:_apply_edit_with_report`):target 落在保护区 → `skipped_protected_slow_update_region`,skill 不变;append/insert_after 一律落在 `SLOW_UPDATE_START` **之前**;edit content 里的 marker 被剥除。
→ 「step 级 edit 不可覆盖受保护字段」由此保证。

### 6. rejected buffer(`trainer.py:1395-1422`)
reject 时把 `score_before/score_after/rejected_edits` 挂进 per-epoch `step_buffer`。**buffer 只作后续 edit 生成的 prompt 上下文,不进入 gate 判定** → 对「逐决策等价」replay 不是决策变量(仅需断言内容构造一致)。

## 决策:K=1 档案如何映射
- $K=1$ → 单 cell,descriptor 不参与。**cell elite 同时扮演 SkillOpt 的 current 与 best**(因二者在 step 循环恒等)。
- QD `U.update(archive, cand, f)` 在 $K=1$ 的接受规则 = `f > E_t(1)` 严格、平局拒 = `evaluate_gate` 的 **accept_new_best/reject**(force-accept 默认配置下 step 循环不出现裸 accept)。
- **T001 范围 = step 选择逻辑**:以 `evaluate_gate` 为 ground-truth oracle,断言 K=1 `U` 逐步产生相同 `action / (current,best,best_step)`。
- epoch 级 slow-update(含 current/best 分叉、受保护字段)**不属于 step 选择逻辑**;T001 用一条独立 case 验证「step edit 不覆盖受保护字段」与 SkillOpt 一致,但**不复现** slow-update 的 LLM 调用。

## 影响
- T001 可把 `evaluate_gate` 直接当 oracle(已是纯函数)→ replay 测试零付费、毫秒级。
- T005(档案 + 格内 gate)直接复用本 ADR 的 elite 语义;$K>1$ 时每 cell 各维护一份「current==best」式 elite。
- **待确认(不阻塞 T001)**:gated 模式下 slow 候选可使 current<best;$K>1$ 的跨格 elite 是否需要区分 current/best?→ 记入 T005 再议。
