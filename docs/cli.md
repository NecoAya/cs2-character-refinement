# 资源块比较器

项目创建、阶段执行和恢复命令见 [执行器文档](runner.md)。本篇仅介绍只读资源比较工具，两者的退出码含义不同。

## 范围

`scripts/compare_resource_blocks.py` 是只读检查工具。它读取 Source 2 已编译资源的头版本 12 块目录，比较块载荷哈希。仓库附带可重复的合成样本测试；已测试基本目录布局不代表兼容所有同头版本资源。

仅依赖 Python 标准库，发布测试环境为 Python 3.12.4 / Windows。工具不会启动游戏、修改模型、写令牌或访问网络。

## 参数

```text
python scripts/compare_resource_blocks.py BASELINE CANDIDATE
       [--allow-changed TAG] [--allow-changed TAG ...] [--enforce]
```

| 参数 | 含义 |
|---|---|
| `BASELINE` | 明确的基线编译文件 |
| `CANDIDATE` | 待检查的候选编译文件 |
| `--allow-changed TAG` | 允许指定四字符块名发生新增、删除或载荷改变；可重复 |
| `--enforce` | 未允许差异导致退出 `1`；省略时只报告 |

允许名单作用于该名称的所有同名块实例，不是只允许某一个节点、字段或具体序号。名单只能表达粗粒度合同，仍需语义检查。

## 示例

只观察差异：

```powershell
python -X utf8 -B scripts/compare_resource_blocks.py baseline.vmdl_c candidate.vmdl_c
```

预期仅编译元数据变化：

```powershell
python -X utf8 -B scripts/compare_resource_blocks.py baseline.vmdl_c candidate.vmdl_c --allow-changed RED2 --enforce
```

某个已明确验证范围的物理候选允许 DATA、PHYS、RED2 变化：

```powershell
python -X utf8 -B scripts/compare_resource_blocks.py baseline.vmdl_c candidate.vmdl_c --allow-changed DATA --allow-changed PHYS --allow-changed RED2 --enforce
```

第三例不是推荐的万能名单。允许 PHYS 变化不等于任意物理变化安全；允许 DATA 变化也不证明骨骼、约束或 hitbox 正确。

## 退出码

| 代码 | 含义 |
|---|---|
| `0` | 成功生成报告；只有使用 `--enforce` 时才同时意味着允许名单检查通过 |
| `1` | 使用 `--enforce` 时发现未允许的载荷/资源版本/尾部数据差异 |
| `2` | 参数、文件读取或解析失败；解析/读取错误 JSON 输出到标准错误，参数错误由 argparse 输出 |

自动检查不要只读 `$LASTEXITCODE` 而忘记是否启用了 `--enforce`。交互分析应同时查看报告字段。

## JSON 字段

- `file_identical`：整个文件 SHA256 是否一致，独立于允许名单。
- `block_directory_sequence_identical`：按读取次序的块标识是否一致。
- `blocks`：每个 `TAG[出现次序]` 的 `same/changed/added/removed` 状态和前后字节数。
- `unexpected_changes`：不在名单内的块，以及资源版本或未解析尾部变化。
- `payload_allowlist_passed`：本工具范围内的允许名单检查是否通过，不是模型验收状态。
- `baseline/candidate`：输入尺寸、头版本、资源版本、哈希、块目录与尾部信息。

## 有意的限制

1. 同名块按出现次序匹配；重新排序可能造成载荷对比变化，不自动做语义身份匹配。
2. 不解码压缩 KV3、顶点/索引、蒙皮或物理参数。
3. 重定位、目录顺序和填充字节变化不单独使允许名单检查失败；文件哈希仍反映整文件不同。
4. 改变资源版本或未解析尾部数据会被列为意外变化；不能靠块名名单放过它们。
5. 不支持的头版本、异常目录、越界或重叠载荷会拒绝解析，不尝试“修好”文件。
6. 哈希证明一致性，不证明文件内容的正确性或授权来源。
7. 错误信息可能包含用户传入的本地文件路径；分享日志前需要脱敏。

更细验证见 [验证方法](validation.md)。
