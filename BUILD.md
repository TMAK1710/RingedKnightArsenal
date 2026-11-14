# 开发与复现边界

公开仓库包含运行逻辑、原生模块、编辑器扩展和部分资产处理流程。**不是附带全部原始工程素材的一键构建仓库**。缺少私人输入时，检查或构建失败应视为缺少依赖，不能删除契约检查来强行编译并声称兼容。

## 原生代码

需要 Visual Studio 2022 C++ x64 工具链、Python 3，以及以下依赖按既定目录准备：

| 路径 | 来源／版本 |
|---|---|
| `tools/native-deps/ue4ss-1ceefac8` | [RE-UE4SS](https://github.com/UE4SS-RE/RE-UE4SS) revision `1ceefac8` 的源码及其一方依赖目录 |
| `tools/UE4SS/ue4ss/UE4SS.dll` | 与 `compatibility.json` SHA256 完全相同的已验证加载器；同版本名称不代表二进制相同 |
| `tools/native-deps/fmt-11.2.0` | [fmt 11.2.0](https://github.com/fmtlib/fmt/tree/11.2.0) |
| `references/pbz-mc/third_party/nlohmann-json-3.11.3` | [nlohmann/json 3.11.3](https://github.com/nlohmann/json/tree/v3.11.3)，`json.hpp` 放在该目录 |
| `references/pbz-mc/third_party/minhook-1.3.4` | [MinHook 1.3.4](https://github.com/TsudaKageyu/minhook/tree/v1.3.4)，保留 `include` / `src` |

`src/build_native.ps1` 根据指定 UE4SS 导出生成导入库，构建原生模块。VS 安装位置不同时先改脚本 `$dev`。临时文件放项目 `build/tmp`。不要使用来历不明或不同引擎版本的 UObject 内存布局替代实际契约。

构建前还需要自行从对应游戏版本准备的契约报告，例如 `reports/runtime-protection-schemas.json`、`reports/armor-0912-makespec-schema.json`、`reports/ue-native-guard-map.txt` 以及检查脚本引用的其他实际结构报告。它们不公开。此发布未重新执行完整原生构建，不承诺只运行这条命令即可复现已安装 DLL。

## Lua 与离线测试

Lua 为 UE4SS 使用的 Lua 5.4。纯模块测试使用 Python 的 `lupa`，例如在独立环境中安装 `lupa` 后运行：

```powershell
python src/test_animation_blend.py
New-Item -ItemType Directory -Force reports
python src/test_native_control_lease.py
```

不是所有测试都自包含。`test_weapon_switch.py` 需要私人报告 `reports/native-weapon-switch-signatures.json`。读取 `combat-profile.json`、游戏反射报告或真实执行文件的测试，需要相应私人输入。`private/game/PBZ.exe` 是测试输入约定，不随仓库提供。离线模拟通过不证明游戏内命中、帧率、特殊处决或交互已通过。

## 美术、动作、声音与游戏资产

使用本人合法取得的游戏和必要 DLC 自行准备输入，并遵守适用授权。仓库不包含解包密钥或规避流程。

- `build_combat_profile.py` 从参数报告、动作数据和模型挂点生成 `combat-profile.json`；`export_blade_tracks.py` 写入与动作匹配的剑身轨迹。
- `retarget_*`、`build_*` 和 `editor/RingedKnightEditor` 提供动作重定向与编辑器辅助逻辑。需要 Blender、对应 UE 编辑器、游戏骨架及材质等私人输入。
- 旧资产工具已将本机绝对路径换成项目根目录或 `build/asset-export`、`private/asset-input`；从仓库根目录运行。它们是开发流程源码，并非无需配置的通用导入器。
- `combat-profile.json`、`item-upgrades.json`、音频、烘焙的 `.pak/.ucas/.utoc` 等属于完整私人构建输入／产物，不在公开仓库里。
- 文件布局必须与 Lua 中 `/HuaShira/Mods/RingedKnight/...` 等资源路径对应。不要把替身骨架、测试材质或原版游戏资源覆盖进发布包。

## 安装包格式

`installer/Setup.ps1` 读取同目录 `manifest.json` 与 `payload/`。清单字段：

```json
{
  "Version": "0.9.16-local",
  "GameSHA256": "SHA256_OF_SUPPORTED_EXE",
  "Files": [
    {"Path": "platform/steam/ue4ss/Mods/RingedKnightArsenal/enabled.txt", "SHA256": "FILE_SHA256", "Kind": "Mod"}
  ]
}
```

`Kind=Mod` 为独占文件；`Loader` 不覆盖不匹配的共享加载器；`Settings` 保留现有设置。完整包还需所有 Lua、私人 JSON、原生 DLL／许可证、音频、两组资产容器，以及匹配 UE4SS 和 `UEHelpers`。两模块各用 `enabled.txt` 启用，不覆盖用户 `mods.txt`。

禁止把原版游戏执行文件、存档、调试队列、崩溃转储、密钥或整套其他 Mod 放进 payload。完整本地素材包不得作为本仓库 Release 上传。

`python installer/test_setup.py` 用临时模拟目录检查安装事务，不启动游戏。输出保存在仓库 `build/release-tests`。
