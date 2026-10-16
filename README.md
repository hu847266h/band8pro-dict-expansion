# 小米手环 8 Pro 英汉词典词库扩充

为手环端词典 App `com.givemefive.dic`（「英汉词典」v1.0.0）扩充词库的构建工具集：
词条数 **40013 → 52609（+31.5%）**，并修复原版一批"词在库里却查不到"的问题。

> 本仓库只包含**构建脚本与文档**，不包含原 App、原词库及成品包。原 App 与原词库的
> 著作权属于其作者；请从你自己的设备/安装包中取得原始文件后，用本工具自行构建。
> 新增词条数据来自 [ECDICT](https://github.com/skywind3000/ECDICT)（MIT License）。

## 它解决了什么问题

原版在手环上查不到很多常见词（如 student、deadline、download），经逆向分析确认有三层原因：

1. **词库真缺词**：与 BNC/COCA 高频前 3000 词对照，缺约 127 个真实常用词/词形；
2. **原始词库排序不严格**（约 1382 处逆序）：App 是顺序扫描 + 提前停止，逆序会跳过条目
   （同条件模拟下原版 1127 个测试词有 70 个查不到）；
3. **索引硬编码在 App 内**：463 个前缀锚点偏移 + 词库大小常量写死在 `pages/index/index.js`，
   只替换词库文件必然错位——必须词库、索引、App 三者成对重建。

另外两个在真机上踩到的坑（详见 [docs/REPORT.md](docs/REPORT.md)）：

- RPK 的 `META-INF/CERT` 是「hash.json 的 zip + 附尾签名段」结构，重打包必须走 aiot
  工具链签名（`SignUtil.signPackage`），否则手环安装时校验失败并重启；
- App 每次只读 200 码元，长桶（如 st 段无中点锚点，student 需 113 次读取）真机上会失败，
  且搜索存在异步竞态——最终版 App 把分块放大到 2000 并给搜索加了代际守卫。

## 格式备忘（逆向结论）

- 词库 `dic.bin`：UTF-16LE 文本，每条两行 `单词\n释义\n`，全表按单词排序；App 从
  `internal://mass/dic.bin` 读取。
- 索引：条目起始**字节偏移**表，键为 1 字母 / 2 字母 / `xy+n` 三类前缀，硬编码在 App 代码中。
- 「词库安装器」是小米表盘 .bin：0x110 起 8 条文件表记录，block 格式为
  `[3B 数据长度 LE][1B 名长][16B 零] + 名 + 数据`；其 Lua 脚本把内嵌 dic 复制到
  `/data/quickapp/mass/com.givemefive.dic/dic.bin`。

## 构建方法

需要 Python 3、Node.js，以及 aiot 工具链（`@aiot-toolkit/aiotpack`，签名步骤用）。

```bash
# 1. 从你自己的安装器 .bin 提取原始词库
python3 src/extract_dic.py <词库安装器.bin> dic-original.bin

# 2. 下载 ECDICT 数据（MIT）并构建扩充词库
curl -L -o ecdict.csv https://raw.githubusercontent.com/skywind3000/ECDICT/master/ecdict.csv
python3 src/build_dic.py dic-original.bin ecdict.csv dic-expanded.bin build-stats.json

# 3. 重打包安装器（只换 dic 段，其余字节不变）
python3 src/patch_installer.py <词库安装器.bin> dic-expanded.bin installer-expanded.bin

# 4. 给 App 重生成索引并 patch（索引/大小常量/版本号），再走工具链签名
python3 src/patch_app.py <原App.rpk> dic-expanded.bin app-patched.rpk   # 内容 patch
node src/sign.mjs <解包目录> app-signed.rpk                              # 工具链签名

# 5. 按 App 真实算法模拟验证（区分“词在文件里”和“App 能查到”）
python3 src/verify_app_sim.py dic-expanded.bin <从App提取的索引.json> dic-original.bin verify-report.json
```

选词规则（`src/build_dic.py`，参数可调）：原词条全部保留；新增 =
考试标签词（中考/高考/四六级/考研/托福/雅思/GRE）∪ BNC/COCA 词频前 20000 ∪
牛津核心 ∪ 柯林斯 ≥4 星 ∪ 少量现代常用词补录；另由 ECDICT exchange 字段生成
词形条目（过去式/分词/三单/复数/比较级等），释义指向词元。

## 验证结果

按 App 真实查询代码逐码元模拟 + 真机实测：原词回归失败 70 → 3（余 3 条为原始数据损坏
条目）；新词、词形、英美变体、多义完整性、编码检查全部通过；真机上 feedback、
deadline、organisation、serendipity、student、stupid 均可查到。

## 许可

- 本仓库脚本与文档：MIT。
- 新增词条数据：ECDICT，MIT（见 `ECDICT-LICENSE.txt`）。
- 原词库与原 App 不属于本仓库，其权利归原作者所有。
