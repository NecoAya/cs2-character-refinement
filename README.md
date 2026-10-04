# CS2 Character Workflow & Refinement

CS2 / Source 2 角色全流程技能：从用户原始资产转模，处理造型材质、官方骨架与约束、第一人称手袖、物理、受击框和持枪，再做优化、编译、排错与交付。

**2.x 已整合完整制作流程与精修方法。** 为保持已安装技能的调用兼容，仓库和技能 ID 仍为 `cs2-character-refinement`。所有阶段在同一个技能入口内，不需要安装另一个工作流。

本仓库提供制作方法、项目模板和执行协调工具。真实角色制作需要使用者提供资产，并具备相应 DCC / Workshop Tools 与工程适配；运行脚本不会自动将任意资产转换为可用模型。上游来源、本仓库的整合与修改及许可状态见 [来源说明](SOURCE.md)。

## 使用入口

- [技能入口](SKILL.md) · [安装与准备](docs/getting-started.md)
- [完整流程及局部迭代](docs/workflow.md) · [阶段合同](references/stages.md)
- [项目创建、阶段记录与恢复](docs/runner.md) · [资源块比较 CLI](docs/cli.md)
- [验证方法](docs/validation.md) · [FAQ](docs/faq.md)
- [版本记录](CHANGELOG.md) · [维护规范](CONTRIBUTING.md) · [隐私](SECURITY.md)

## 全流程覆盖

| 阶段 | 制作内容 | 重点参考 |
|---|---|---|
| 1. 资产审查 | Unity/FBX/Blender/DMX、服装、原材质、表情、工具、单位与输入清单 | [输入与造型](references/intake-and-appearance.md) |
| 2. 外观制作 | 比例、造型、肤色、眼睛、alpha、金属、宝石、颜色层和装饰 | [材质与优化](references/materials-and-optimization.md) |
| 3. 骨架适配 | 官方动画骨、角色变形骨、映射、约束、bind 变换及编译保留 | [骨架与约束](references/rig-and-constraints.md) |
| 4. 第一人称 | 用户提供的基础手、袖套、指甲、戒指、腕缝和视角分组 | [第一人称](references/firstperson.md) |
| 5. 物理 | 飘骨、裙摆布料、固定根、碰撞、PB 参考、分段柔软度和回正 | [物理响应](references/physics.md) · [次级运动](references/secondary-motion.md) |
| 6. 受击框 | 骨绑定、端点坐标、伤害组及服务端姿态 | [持枪与受击框](references/holding-and-hitboxes.md) |
| 7. 持枪 | 一个角色模型适配官方动作、左右手目标、多武器与站蹲 | [持枪与受击框](references/holding-and-hitboxes.md) |
| 8. 优化 | 减面、贴图分辨率/压缩、实际依赖预算、LOD、draw call 与物理成本 | [材质与优化](references/materials-and-optimization.md) |
| 9–11. 编译与交付 | 编译日志、成品语义、依赖闭包、包校验、版本记录和回退 | [验证与交付](references/validation-and-delivery.md) |

也覆盖网格消失、AO 和 alpha 溢出、局部材质丢色、受光异常、次级运动不稳定、骨骼轴向、ERROR 和补丁兼容性。检查方法区分源、编译、离线回归与游戏观察，避免把联合改动归因于单一原因。

## 调用示例

```text
使用 $cs2-character-refinement 将我提供的角色资产转成 CS2 模型。
自动推进完整流程，第一人称手使用我提供的基础素材。
保留表情数据；检查官方骨骼与约束，完成手袖、物理、持枪和优化。
每阶段记录产物与验证，每版本留痕，交付候选让我游戏验收。
```

```text
使用 $cs2-character-refinement 修复第一人称手的姿态。
先检查官方骨架、约束和编译映射，再判断网格或权重是否需要修改。
从已接受版制作候选，保留非目标网格、物理和材质。
```

## 实际执行能力

当前 Codex 使用用户工程和本机 DCC / Workshop Tools 完成具体制作；本仓库附带的 Python 工具负责以下可重复工作：

- 创建通用项目配置，核验可选外部手模清单。
- 协调 11 个阶段，执行已配置命令 adapter，记录作者阶段证据。
- 保存文件哈希与快照，检测配置/已完成输出变化，按指定检查点暂停与恢复。
- 只读比较 Source 2 资源块，执行合成测试和发布文件检查。

创建配置和运行协调器不会自行完成 DCC 建模、动画解算、编译或游戏测试。真实操作需要当前角色的映射、工具与 adapter；`needs_authoring` 是作者工作待执行的状态。空模板不能证明模型已完成，运行时未测状态保留在报告中。

仓库不附带人物、基础手、贴图或游戏文件，手模由使用者提供。换装及表情/嘴型接口提供制作合同和配置规划，默认标记为预留，游戏控制需实际实现。个人模型的工程、参数、候选记录和反馈保存在使用者工程中；公开截图或预览图须由权利人明确选择并检查内容。

## 脚本起步

在技能仓库根目录运行，示例资产和输出位于该目录之外：

```powershell
python -X utf8 -B scripts/create_project.py --id new_character --source ../character-assets --workspace ../character-project
python -X utf8 -B scripts/workflow.py plan ../character-project/project.json
python -X utf8 -B scripts/workflow.py start ../character-project/project.json --run ../character-project/run-001
```

`../character-assets` 是已有的用户资产目录，`../character-project` 必须是新目录。两者均放在技能仓库之外，输出不能位于原资产内。请按实际工程位置替换这些路径，不把模型、配置、日志或快照放进技能仓库。阶段需要 authoring 时退出 `2`，随后继续实际制作和记录，见 [执行器说明](docs/runner.md)。

## 验证与环境

```powershell
python -X utf8 -B scripts/validate_project.py
python -X utf8 -B -m unittest discover -s scripts -p "test_*.py" -v
```

脚本只依赖 Python 标准库，发布验证环境为 Python 3.12.4 / Windows。合成测试覆盖协调器、路径边界、快照、证据记录和资源比较器；真实角色仍需源、导出、编译、离线及用户游戏验收。没有配置 CI、自动安装或自动发布。

## 项目结构

```text
cs2-character-refinement/
├── SKILL.md                 统一入口
├── agents/openai.yaml       技能显示与匹配信息
├── references/              全流程合同、专题排错和通用验证示例
├── assets/                  新项目、换装及表情配置模板
├── scripts/                 创建、协调、比较、检查及测试
├── examples/                任务与阶段证据示例
├── docs/                    安装、流程、执行器、验证和 FAQ
├── SOURCE.md                 上游来源、修改与许可说明
└── CHANGELOG.md              技能版本记录
```

[验证示例](references/evidence-case.md) 说明不同检查能支持的结论及其边界，不包含个人模型履历，也不作为参数配方。X 轴沿骨链、指向身体中心与朝向角色前方需明确区分，详见 [轴向](references/axes-and-binding.md)。

本仓库可公开下载；下载与发布不会自动安装到本机，也不会修改角色。仓库由所有者维护，协作方式见 [维护规范](CONTRIBUTING.md)。此项目非 Valve / OpenAI 官方项目，暂未指定开源许可证；公开可见不改变上游及第三方的许可状态，模型素材的授权也不随技能仓库转移。

## 特别感谢 Ruiyi Welkin、雨夜听风眠 等 大佬们的帮助（排名不分先后
参考了雨夜大佬的skill：https://github.com/rainyKnight/cs2-character-workflow
