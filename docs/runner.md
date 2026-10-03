# 项目创建、阶段执行与恢复

执行器协调制作顺序、证据、快照和用户选定检查点。阶段 authoring 由当前 Codex 和项目工具完成，脚本自身没有 DCC 转换器、物理解算或游戏控制。工具仅用 Python 标准库，发布测试环境为 Python 3.12.4 / Windows。

## 创建项目

在技能仓库根目录调用；示例资产和工程位于技能仓库之外：

```powershell
python -X utf8 -B scripts/create_project.py --id new_character --source ../character-assets --workspace ../character-project
```

`--source` 必须存在，可以是源目录或文件。`--workspace` 必须是不存在的新目录，不能放进源目录；原资产只读。两者均使用技能仓库外的路径，按实际位置替换示例。ID 使用小写字母开头和小写字母/数字/下划线。工程内 `project.json` 记录实际路径；真实配置、日志、快照和作者产物保存在角色工程，不提交到技能仓库。

需要用户检查点或外部手清单时：

```powershell
python -X utf8 -B scripts/create_project.py --id new_character --source ../character-assets --workspace ../character-project --checkpoint appearance --checkpoint firstperson --hand-manifest ../hand-assets/manifest.json
```

检查点可重复指定，名称必须是阶段 ID。不指定时模式为 `auto`，指定时为 `checkpoints`。快照两种模式均自动保存。

手清单引用 manifest 目录下的真实文件，路径不能逃出该目录，SHA256 必须匹配。例如结构：

```json
{"files": {"hands.dmx": {"sha256": "填入真实文件的64位SHA256"}}}
```

上例是格式说明，不能原样通过检查。仓库不附带手资产；无 `--hand-manifest` 时可先建立工程，第一人称阶段仍需要真实输入或当前工程授权制作。

## 编辑合同，再开始 run

模板的默认 11 个阶段都是 `kind: agent`，表示作者实际执行。填写选装/造型、物理意图、预算、工具和输入。换装/表情默认 `reserve`，运行控制保持未实现。

每阶段默认 `outputs` 有 `result.json`、自己的 `wardrobe.json` 和 `expressions.json`。把该阶段关键的真实场景、DMX、VMDL、材质、报告或包加入 `outputs`；它们必须位于 run 下，路径不能逃逸、重复占用其他阶段输出或覆盖状态/快照/日志。否则协调器只能快照列出的 JSON，不能备份其引用的外部资产。

下游修改自己的副本，不改以前完成的阶段输出。未来新增产物或 adapter 会改变配置，需要新 variant/run。源资产哈希、工具和语义检查由阶段报告维护，协调器的哈希检查仅覆盖配置和显式输出文件。

查看并开始：

```powershell
python -X utf8 -B scripts/workflow.py plan ../character-project/project.json
python -X utf8 -B scripts/workflow.py start ../character-project/project.json --run ../character-project/run-001
```

`--run` 必须是新目录，配置复制为 `config.json`，进度保存到 `state.json`。作者阶段输出 `NEEDS_AUTHORING intake` 并退出 `2` 时，当前 Codex 继续完成 intake，不是用户必须重新发“继续”。

## 完成作者阶段

执行真实阶段，创建全部合同文件。在项目内复制 [证据模板](../examples/stage-evidence.json)，写实际方法、测量、报告路径、限制与逐项检查。模板 `status: not_run`，不能拿来当通过结果。

`record` 要求非空 summary、总体 `passed`，以及非空 checks 列表；每项有 name 和 `status: passed`。只记录已完成且实际通过的检查，待游戏验收项放进 limitations/runtime_acceptance，不伪造已经通过。

```powershell
python -X utf8 -B scripts/workflow.py record ../character-project/run-001 intake --evidence ../character-project/intake-evidence.json
```

全部输出存在后，协调器保存 SHA256、字节数和 `checkpoints/<stage>/` 文件副本，并将 evidence 嵌入 receipt。它验证证据结构和文件合同，不判断陈述是否真实或模型是否正确，真实检查仍由作者负责。

record 后自动推进下一阶段；遇下个作者任务、用户检查点或失败才停止。空模板、假通过证据和未列入 outputs 的实际文件都不能作为制作完成依据。

## 检查点与恢复

```powershell
python -X utf8 -B scripts/workflow.py status ../character-project/run-001
python -X utf8 -B scripts/workflow.py resume ../character-project/run-001
```

已完成输出和快照逐文件哈希不变、配置不变时恢复。输出或快照丢失/变动会拒绝继续；正确做法是找到问题或建新候选，不修改记录哈希来放行。阶段失败先看对应 `logs/<stage>.log` 和错误状态，再修相关 adapter 或开新变体。

指定检查点完成后状态为 `awaiting_review`。给用户实际预览/候选，在收到真实反馈后记录：

```powershell
python -X utf8 -B scripts/workflow.py accept ../character-project/run-001 appearance --note "记录实际用户反馈与接受范围"
```

不把占位句当真实反馈执行。accept 只在对应等待阶段有效；没有用户检查点时无需每阶段询问。脚本允许操作者显式接受，但执行技能的 Codex 必须遵守当前用户指定的检查点。

## 命令 adapter

现有可靠工具可将阶段改为 `kind: command`，指定 argv 数组、输出合同和可选成功标记。例如配置结构：

```json
{
  "id": "compile",
  "kind": "command",
  "argv": ["{python}", "{adapter}", "--run", "{run}"],
  "success_marker": "COMPILE_VALIDATED",
  "outputs": ["stages/compile/result.json", "stages/compile/model.vmdl_c"]
}
```

`adapter` 由 `variables` 指向当前工程中真实存在的编译/检查脚本。内置占位符有 `{python}`、`{skill}`、`{run}`、`{config}`。命令工作目录为 run，stdout/stderr 合并到日志；调用不经过 shell，但 adapter 仍有当前操作者权限，必须审阅真实命令，执行器不是隔离沙箱。

退出非零、成功标记缺失或合同文件缺失都失败。退出零加标记只说明 adapter 声明完成，仍需其真实日志/产物/断言。成功标记应在断言全通过后输出，不能一开始就打印。

## 状态与退出码

| 状态 | 含义 |
|---|---|
| `needs_authoring` | 当前作者阶段尚待实际制作并 record |
| `awaiting_review` | 用户指定检查点等待接受 |
| `failed` | 命令或合同失败，查日志和错误 |
| `complete` | 配置阶段和指定检查点完成，具体游戏待测项仍看报告 |

`start/resume/record/accept`：`0` 完成配置流程，`2` 等待 authoring/review，`1` 失败。`plan/status` 成功返回 `0`。块比较器的退出码另见 [CLI](cli.md)，不要混用。

## 局部修复与版本记录

完整阶段可选择复用明确基线的产物，但要登记来源、哈希、未改内容与重验范围。局部配置可只包含所需阶段；不能借减少阶段来省略依赖和回归。

每个候选记录时间、目标、假设、实际改动、保护项、源/编译/离线状态、反馈及恢复对象。历史接受版和补丁底包保持可恢复。协调器不自动生成全部角色版本日志，也不推断阶段依赖；作者按 [流程](workflow.md) 和 [交付](../references/validation-and-delivery.md) 维护。
