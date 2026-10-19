# 第三方代码与许可声明

本项目在实现分级阅读的"分词与渲染项计算"时，参考并改写了 Lute 的算法。
以下按 MIT 许可的要求保留版权与许可声明。

## Lute (https://github.com/LuteOrg/lute-v3)

- 许可：MIT License，Copyright (c) 2023 Jeff Zohrab
- 被参考/改写的文件：
  - `lute/read/render/calculate_textitems.py` —— 重叠渲染项的消解算法
    （按 `(index, -token_count)` 排序后**从后往前**写入占位数组，再用 `display_count`
    决定真正渲染的项；`display_text` 取末尾若干个 token）
  - `lute/read/render/text_item.py` —— TextItem 的展示契约
    （`display_text` / `status_class` / `span_id` 的形式）
- 本项目落地位置：`backend/app/reading/textitems.py`
- 改写要点（未引入其 Flask/Jinja 运行时与 Term 数据模型）：
  - 分词改用正则实现，不依赖按语言的 parser；
  - "term" 来自本项目公共词库 `words` 表（精确匹配 headword），
    掌握状态来自当前用户自己的学习记录；
  - 输出为普通 dict，由 FastAPI 直接序列化。
- 未复制的部分：Lute 的示例文章、数据库结构、模板与界面样式。

### MIT License 全文

```
MIT License

Copyright (c) 2023 Jeff Zohrab

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## 阅读文章内容

`backend/app/data/reading_articles.json` 中的文章与题目均为**本项目原创示例**，
用于功能演示，不是任何官方考试的真题或模拟题，也未抓取任何外部文章。