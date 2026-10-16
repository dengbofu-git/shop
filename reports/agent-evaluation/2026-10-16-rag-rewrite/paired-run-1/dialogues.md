# 真实模型对照：30次完整问答

A=同一Agent关闭查询改写，使用旧单查询检索；B=同一Agent启用0.9.0查询链路。
以下回答直接来自原始JSONL，不用修改后的答案替换。每题独立公开会话，未传入真实客户历史。

## 01 · 中文加工比较

**用户：** 绿茶和红茶在制作工艺上有什么区别？

预先固定目标：解释绿茶加热钝化酶、红茶酶促氧化的区别。

### A · 单查询

绿茶与红茶在制作工艺上的核心区别在于**是否经过有意的酶促氧化（行业内常称为“发酵”）**。

**绿茶**：鲜叶采摘后迅速加热（杀青），使酶失活，从而阻止氧化；之后可能经过揉捻、做形或粉碎、干燥等步骤。绿茶基本不进行有意的氧化。（来源：ISO 20715:2023 Tea — Classification of tea types）

**红茶**：制作中会经历“发酵”环节。这里的“发酵”是行业用语，指叶片细胞破损后暴露于空气所发生的**酶促氧化**，与微生物发酵不同。红茶正是通过这一氧化过程形成其品质特征。（来源：Fermentation: The Key Step in Processing of Black Tea）

**一句话对比**：绿茶以“杀青”终止氧化，红茶以“酶促氧化”为核心工艺步骤。

补充说明：具体加热方式、做形方式会因产地和产品而异；另外，茶树品种与茶类是两个概念，同一品种用不同工艺可制成不同茶类，因此工艺对成品茶类型起关键作用。（来源：ISO 20715:2023；Impact of Six Typical Processing Methods on the Chemical Composition of Tea Leaves）

如需了解具体某款绿茶或红茶的工艺或商品信息，可以告诉我茶名，我再帮你查询。

**人工复核：** 完成；区分绿茶加热钝化酶与红茶酶促氧化，关键事实受65/81片段支持。

耗时 18.617s；模型调用 2；Token 输入 4504 / 输出 600。

最终支持点指标：`{"selected_ids": [65, 81, 68, 78, 79], "support_groups_hit": 2, "support_groups_total": 2, "support_group_coverage": 1.0, "all_available_support": true, "labelled_relevant_precision": 0.4}`。

查询与补检实际记录：

```json
[]
```

实际来源：

- [ISO 20715:2023 Tea — Classification of tea types](https://www.iso.org/obp/ui?_escaped_fragment_=iso%3Astd%3Aiso%3A20715%3Aed-1%3Av1%3Aen)
- [Fermentation: The Key Step in Processing of Black Tea](https://agris.fao.org/search/fr/records/6473b0a3542a3f9f03b31231)
- [Impact of Six Typical Processing Methods on the Chemical Composition of Tea Leaves](https://agris.fao.org/search/en/records/65dff5d763b8185d9cb04493)
- [Tea Board India — Modalities and Scheme Guidelines](https://www.teaboard.gov.in/pdf/schemes/Modalities_and_scheme_guidelines_12th_Plan.pdf)

### B · 查询改写

**绿茶与红茶在制作工艺上的核心区别**

- **绿茶**：对鲜叶快速加热以钝化酶活性，之后可能经过揉捻、做形或粉碎、干燥等步骤。关键点是**不经过红茶那种有意的氧化（发酵）处理**。具体加热方式和外形因产地和产品而异。（来源：ISO 20715:2023 Tea — Classification of tea types）
- **红茶**：在叶片被破坏并接触空气后，进行**酶促氧化**，行业里常把这一步叫做“发酵”，但它与微生物发酵不同。红茶属于有意氧化，而绿茶则几乎不进行有意氧化。（来源：Fermentation: The Key Step in Processing of Black Tea）

**一句话对比**：绿茶靠“杀青”终止氧化，红茶靠“发酵（酶促氧化）”促成氧化，这是两者工艺上最本质的分界。

**补充说明**：茶树品种与茶类是两个概念，同一品种用不同工艺可制成不同茶类，因此工艺对成品类型起决定作用。（来源：Impact of Six Typical Processing Methods on the Chemical Composition of Tea Leaves）

如需进一步了解具体商品，请告诉我您的口味偏好或预算，我再为您查询实时价格与库存。

**人工复核：** 完成；正确解释同一加工区别，关键支持片段与A相同；额外有推荐引导。

耗时 15.348s；模型调用 3；Token 输入 5770 / 输出 692。

最终支持点指标：`{"selected_ids": [65, 81, 68, 78, 79], "support_groups_hit": 2, "support_groups_total": 2, "support_group_coverage": 1.0, "all_available_support": true, "labelled_relevant_precision": 0.4}`。

查询与补检实际记录：

```json
[
  {
    "original_query": "绿茶和红茶在制作工艺上有什么区别?",
    "rewrite_status": [
      "translated"
    ],
    "rewrite_error_types": [],
    "rejected_variants": 0,
    "queries": [
      {
        "round": 0,
        "query": "绿茶和红茶在制作工艺上有什么区别?",
        "limit": 15,
        "hits": 15,
        "status": "success"
      },
      {
        "round": 0,
        "query": "What are the differences between green tea and black tea in terms of production process?",
        "limit": 5,
        "hits": 5,
        "status": "success"
      },
      {
        "round": 0,
        "query": "绿茶和红茶在制作工艺上有什么区别? | green tea black tea 加工 processing",
        "limit": 5,
        "hits": 5,
        "status": "success"
      },
      {
        "round": 0,
        "query": "绿茶与红茶在加工工艺上有哪些区别?",
        "limit": 5,
        "hits": 5,
        "status": "success"
      }
    ],
    "rerank_status": [
      "success"
    ],
    "retry": false,
    "retry_adopted": false,
    "retry_reasons": [],
    "selected_ids": [
      "65",
      "81",
      "68",
      "78",
      "79"
    ],
    "remaining_issues": [],
    "missing_subjects": []
  }
]
```

实际来源：

- [ISO 20715:2023 Tea — Classification of tea types](https://www.iso.org/obp/ui?_escaped_fragment_=iso%3Astd%3Aiso%3A20715%3Aed-1%3Av1%3Aen)
- [Fermentation: The Key Step in Processing of Black Tea](https://agris.fao.org/search/fr/records/6473b0a3542a3f9f03b31231)
- [Impact of Six Typical Processing Methods on the Chemical Composition of Tea Leaves](https://agris.fao.org/search/en/records/65dff5d763b8185d9cb04493)
- [Tea Board India — Modalities and Scheme Guidelines](https://www.teaboard.gov.in/pdf/schemes/Modalities_and_scheme_guidelines_12th_Plan.pdf)

## 02 · 英文加工比较

**用户：** Explain how green tea and black tea differ in their manufacturing processes.

预先固定目标：解释绿茶加热钝化酶、红茶酶促氧化的区别。

### A · 单查询

**绿茶与红茶制造工艺的区别**

根据现有证据，两者最核心的工艺差异在于**是否经过有意的酶促氧化（常被称为“发酵”）**：

- **绿茶**：对鲜叶快速加热以灭活酶，随后可能包括揉捻、做形或粉碎、干燥等步骤。其定义性特征是**不经过红茶工艺中那种有意的通气/氧化**。具体加热方式和外形因地区和产品而异。（来源：ISO 20715:2023 Tea — Classification of tea types）

- **红茶**：在叶片破损并暴露于空气后，进行酶促氧化，行业术语中常把这一步称为“发酵”，但它与微生物发酵不同。绿茶则几乎或完全没有有意氧化；乌龙茶为部分氧化；黑茶可能另有渥堆或后发酵阶段。（来源：Fermentation: The Key Step in Processing of Black Tea）

**补充说明**

- ISO 20715:2023 按制造工艺将茶树（Camellia sinensis）制成的茶分为六类：红茶、绿茶、白茶、乌龙茶、黄茶、黑茶。不使用茶树的草本或水果冲泡饮品不属于这六类。（来源：ISO 20715:2023 Tea — Classification of tea types）
- 茶树品种与茶类是两个不同概念：同一品种用六种典型工艺加工可产生不同的化学成分，因此品种本身并不决定成品茶类或香气，工艺同样重要。（来源：Impact of Six Typical Processing Methods on the Chemical Composition of Tea Leaves）
- Orthodox（传统工艺）与 CTC（crush, tear, curl，即压碎、撕裂、卷曲）是制造方式，与六大茶类的分类维度不同；Orthodox 可用于红茶和绿茶，CTC 常用于浓强冲泡和茶包。市场用词可能不同，建议核对产品标签和地区标准。（来源：Tea Board India — Modalities and Scheme Guidelines）

以上为工艺差异的说明，未涉及具体商品的价格、库存或风味用途；这些属性本次未提供，无法验证。

**人工复核：** 完成；英文输入被正确理解，绿茶/红茶核心区别有证据；回答包含额外制造分类背景。

耗时 17.297s；模型调用 2；Token 输入 4741 / 输出 895。

最终支持点指标：`{"selected_ids": [65, 81, 63, 78, 79], "support_groups_hit": 2, "support_groups_total": 2, "support_group_coverage": 1.0, "all_available_support": true, "labelled_relevant_precision": 0.4}`。

查询与补检实际记录：

```json
[]
```

实际来源：

- [ISO 20715:2023 Tea — Classification of tea types](https://www.iso.org/obp/ui?_escaped_fragment_=iso%3Astd%3Aiso%3A20715%3Aed-1%3Av1%3Aen)
- [Fermentation: The Key Step in Processing of Black Tea](https://agris.fao.org/search/fr/records/6473b0a3542a3f9f03b31231)
- [Impact of Six Typical Processing Methods on the Chemical Composition of Tea Leaves](https://agris.fao.org/search/en/records/65dff5d763b8185d9cb04493)
- [Tea Board India — Modalities and Scheme Guidelines](https://www.teaboard.gov.in/pdf/schemes/Modalities_and_scheme_guidelines_12th_Plan.pdf)

### B · 查询改写

绿茶与红茶的主要区别在于鲜叶是否被有意氧化（茶行业常称之为“发酵”）。

**绿茶**
- 鲜叶经快速加热以钝化酶活性。
- 随后可能包括揉捻、做形或粉碎等步骤，然后干燥。
- 与红茶的决定性区别：绿茶**不经过红茶工艺中的有意通气/氧化**。
- 具体加热方式和叶形因地区和产品而异。
- 来源：ISO 20715:2023《茶——茶类分类》（记录中未注明年份）。

**红茶**
- 加工包括萎凋、揉捻或切碎、通气/氧化和干燥。
- 茶行业常用“发酵”一词指这一酶促氧化步骤；它**并不**必然指微生物使叶片发酵。
- 这就是红茶被称为氧化茶的原因。
- 来源：ISO 20715:2023《茶——茶类分类》（记录中未注明年份）。

**关于“发酵”一词**
- 在红茶制造中，“发酵”通常指叶片破损并暴露于空气后的酶促氧化，区别于微生物发酵。
- 绿茶几乎或完全不经过有意氧化，乌龙茶为部分氧化；黑茶可能涉及单独的渥堆或后发酵阶段。
- 来源：Fermentation: The Key Step in Processing of Black Tea（记录中未注明年份）。

**相关说明**
- 茶树品种与茶类是不同的概念：品种描述栽培植物的选育，而红茶、绿茶、乌龙茶、白茶、黄茶和黑茶描述的是加工产品类型。加工方式也很重要，并非仅由品种决定。
- 来源：Impact of Six Typical Processing Methods on the Chemical Composition of Tea Leaves（记录中未注明年份）。

我在此没有关于风味或用途属性的可靠信息，因此无法就这些方面作出说明。

**人工复核：** 完成；补充召回64片段，红茶萎凋、揉捻/切碎、氧化、干燥的步骤说明更具体。

耗时 16.325s；模型调用 3；Token 输入 6014 / 输出 946。

最终支持点指标：`{"selected_ids": [65, 81, 64, 78, 79], "support_groups_hit": 2, "support_groups_total": 2, "support_group_coverage": 1.0, "all_available_support": true, "labelled_relevant_precision": 0.6}`。

查询与补检实际记录：

```json
[
  {
    "original_query": "Explain how green tea and black tea differ in their manufacturing processes.",
    "rewrite_status": [
      "translated"
    ],
    "rewrite_error_types": [],
    "rejected_variants": 0,
    "queries": [
      {
        "round": 0,
        "query": "Explain how green tea and black tea differ in their manufacturing processes.",
        "limit": 15,
        "hits": 15,
        "status": "success"
      },
      {
        "round": 0,
        "query": "解释绿茶和红茶在制造工艺上有何不同。",
        "limit": 5,
        "hits": 5,
        "status": "success"
      },
      {
        "round": 0,
        "query": "Explain how green tea and black tea differ in their manufacturing processes. | 绿茶 红茶 加工 processing",
        "limit": 5,
        "hits": 5,
        "status": "success"
      },
      {
        "round": 0,
        "query": "绿茶与红茶在制作工艺上的区别是什么?",
        "limit": 5,
        "hits": 5,
        "status": "success"
      }
    ],
    "rerank_status": [
      "success"
    ],
    "retry": false,
    "retry_adopted": false,
    "retry_reasons": [],
    "selected_ids": [
      "65",
      "81",
      "64",
      "78",
      "79"
    ],
    "remaining_issues": [],
    "missing_subjects": []
  }
]
```

实际来源：

- [ISO 20715:2023 Tea — Classification of tea types](https://www.iso.org/obp/ui?_escaped_fragment_=iso%3Astd%3Aiso%3A20715%3Aed-1%3Av1%3Aen)
- [Fermentation: The Key Step in Processing of Black Tea](https://agris.fao.org/search/fr/records/6473b0a3542a3f9f03b31231)
- [Impact of Six Typical Processing Methods on the Chemical Composition of Tea Leaves](https://agris.fao.org/search/en/records/65dff5d763b8185d9cb04493)
- [Tea Board India — Modalities and Scheme Guidelines](https://www.teaboard.gov.in/pdf/schemes/Modalities_and_scheme_guidelines_12th_Plan.pdf)

## 03 · 中英混合加工比较

**用户：** 请比较green tea和红茶的processing，说明关键区别。

预先固定目标：理解混合语言，比较绿茶与红茶加工。

### A · 单查询

**绿茶与红茶的加工（processing）关键区别**

**绿茶（green tea）**
- 鲜叶采摘后**迅速加热（杀青）**，使酶失活。
- 之后可能包括揉捻、整形或粉碎、干燥等步骤。
- 具体加热方式和外形因产地和产品而异。
- 核心特点：**不经过红茶式的刻意充气/氧化处理**，氧化程度很低或基本没有。

**红茶（black tea）**
- 关键步骤是**叶片破损并暴露于空气后的酶促氧化**（行业内常称“发酵”，fermentation）。
- 这里的“发酵”指**酶促氧化**，与微生物发酵不同。
- 红茶属于**刻意氧化**的茶类；乌龙茶为部分氧化；黑茶可能另有渥堆或后发酵阶段。

**关键区别一句话**
绿茶靠**快速加热灭酶、几乎不氧化**；红茶靠**破损叶片+暴露空气进行酶促氧化**。这就是两者加工上最本质的分界。

**补充说明**
- 茶树品种（cultivar）与茶类（green/black/oolong等）是两个概念；同一品种用不同加工方式可得到不同化学成分特征，因此**加工方式对成品茶类型和香气有决定作用**。
- Orthodox（传统工艺）与 CTC（crush, tear, curl）是**制造方式**，与六大茶类的分类不是同一维度；红茶和绿茶都可有 orthodox 生产。

**来源**
- ISO 20715:2023 Tea — Classification of tea types（年份：2023）
- Fermentation: The Key Step in Processing of Black Tea（年份：未标注）
- Impact of Six Typical Processing Methods on the Chemical Composition of Tea Leaves（年份：未标注）
- Tea Board India — Modalities and Scheme Guidelines（年份：未标注）

**说明**：以上仅为加工工艺层面的比较；未检索到证据的具体风味、用途等属性，无法验证，不作推断。

**人工复核：** 完成；理解green tea/红茶/processing混合输入，核心区别正确；补充称加工对香气有决定作用的措辞偏强。

耗时 22.143s；模型调用 2；Token 输入 4707 / 输出 879。

最终支持点指标：`{"selected_ids": [65, 81, 78, 79, 73], "support_groups_hit": 2, "support_groups_total": 2, "support_group_coverage": 1.0, "all_available_support": true, "labelled_relevant_precision": 0.4}`。

查询与补检实际记录：

```json
[]
```

实际来源：

- [ISO 20715:2023 Tea — Classification of tea types](https://www.iso.org/obp/ui?_escaped_fragment_=iso%3Astd%3Aiso%3A20715%3Aed-1%3Av1%3Aen)
- [Fermentation: The Key Step in Processing of Black Tea](https://agris.fao.org/search/fr/records/6473b0a3542a3f9f03b31231)
- [Impact of Six Typical Processing Methods on the Chemical Composition of Tea Leaves](https://agris.fao.org/search/en/records/65dff5d763b8185d9cb04493)
- [Tea Board India — Modalities and Scheme Guidelines](https://www.teaboard.gov.in/pdf/schemes/Modalities_and_scheme_guidelines_12th_Plan.pdf)

### B · 查询改写

**绿茶与红茶的加工（processing）关键区别**

**绿茶（green tea）**
- 关键步骤：对鲜叶快速加热（杀青）以钝化酶，随后可能包括揉捻、做形或粉碎、干燥。
- 核心特点：**不经过红茶那种有意的通气/氧化过程**。
- 具体加热方式和外形因地区和产品而异。
- 来源：ISO 20715:2023 Tea — Classification of tea types

**红茶（black tea）**
- 关键步骤：萎凋 → 揉捻或切碎（maceration）→ 通气/氧化（aeration/oxidation）→ 干燥。
- 核心特点：行业里常说的“发酵（fermentation）”通常指**叶片破损并接触空气后的酶促氧化**，并不一定指微生物发酵。
- 这也是红茶被称为“氧化茶”的原因。
- 来源：ISO 20715:2023 Tea — Classification of tea types；Fermentation: The Key Step in Processing of Black Tea

**关键区别总结**
1. **是否刻意氧化**：绿茶几乎不进行有意氧化；红茶则经过有意的通气/氧化步骤。
2. **“发酵”含义**：红茶加工中的“发酵”多指酶促氧化，而非微生物发酵；绿茶不涉及这一步骤。
3. **工艺顺序**：绿茶以快速加热钝化酶为起点；红茶以萎凋、揉捻/切碎后氧化为核心环节。

**补充说明**
- 茶树品种（cultivar）与茶类（tea type）是不同概念；同一品种用不同加工方法可产生不同化学成分特征，因此加工方式对成品茶类型和香气有重要影响。
- 来源：Impact of Six Typical Processing Methods on the Chemical Composition of Tea Leaves

**无法验证的内容**
- 本次工具结果未提供绿茶与红茶在具体风味、用途上的对比数据，因此无法验证相关风味或用途差异。
- 未检索到关于进口量或消费量的证据，且进口量不能等同消费量，故不提供此类数据。

如需进一步了解某一茶类的具体加工细节，可继续提问。

**人工复核：** 完成；理解混合语言并增加红茶完整加工步骤，主要结论有证据；存在无关的贸易数据免责声明。

耗时 20.778s；模型调用 3；Token 输入 6065 / 输出 1093。

最终支持点指标：`{"selected_ids": [65, 81, 64, 78, 79], "support_groups_hit": 2, "support_groups_total": 2, "support_group_coverage": 1.0, "all_available_support": true, "labelled_relevant_precision": 0.6}`。

查询与补检实际记录：

```json
[
  {
    "original_query": "请比较green tea和红茶的processing,说明关键区别。",
    "rewrite_status": [
      "translated"
    ],
    "rewrite_error_types": [],
    "rejected_variants": 0,
    "queries": [
      {
        "round": 0,
        "query": "请比较green tea和红茶的processing,说明关键区别。",
        "limit": 15,
        "hits": 15,
        "status": "success"
      },
      {
        "round": 0,
        "query": "Please compare the processing of green tea and black tea, and explain the key differences.",
        "limit": 5,
        "hits": 5,
        "status": "success"
      },
      {
        "round": 0,
        "query": "请比较绿茶和红茶的加工工艺,说明关键区别。",
        "limit": 5,
        "hits": 5,
        "status": "success"
      },
      {
        "round": 0,
        "query": "请比较green tea和红茶的processing,说明关键区别。 | 绿茶 black tea 加工",
        "limit": 5,
        "hits": 5,
        "status": "success"
      }
    ],
    "rerank_status": [
      "success"
    ],
    "retry": false,
    "retry_adopted": false,
    "retry_reasons": [],
    "selected_ids": [
      "65",
      "81",
      "64",
      "78",
      "79"
    ],
    "remaining_issues": [],
    "missing_subjects": []
  }
]
```

实际来源：

- [ISO 20715:2023 Tea — Classification of tea types](https://www.iso.org/obp/ui?_escaped_fragment_=iso%3Astd%3Aiso%3A20715%3Aed-1%3Av1%3Aen)
- [Fermentation: The Key Step in Processing of Black Tea](https://agris.fao.org/search/fr/records/6473b0a3542a3f9f03b31231)
- [Impact of Six Typical Processing Methods on the Chemical Composition of Tea Leaves](https://agris.fao.org/search/en/records/65dff5d763b8185d9cb04493)
- [Tea Board India — Modalities and Scheme Guidelines](https://www.teaboard.gov.in/pdf/schemes/Modalities_and_scheme_guidelines_12th_Plan.pdf)

## 04 · 阿拉伯文加工比较

**用户：** اشرح الفرق بين تصنيع الشاي الأخضر والشاي الأسود.

预先固定目标：识别阿拉伯文绿茶、红茶，比较制造工艺；回答可使用中文。

### A · 单查询

# الفرق بين تصنيع الشاي الأخضر والشاي الأسود

## الفرق الجوهري
الفرق الأساسي هو **الأكسدة الإنزيمية المتعمَّدة**:

- **الشاي الأخضر**: يُصنع بتطبيق حرارة سريعة على الأوراق الطازجة لتعطيل الإنزيمات، ثم قد تشمل الخطوات اللفّ والتشكيل أو التقطيع والتجفيف. السمة المميزة أنه **لا يُهوّى/يُؤكسَد عمدًا** كما في عملية الشاي الأسود. تختلف طرق التسخين والأشكال حسب المنطقة والمنتج.
  - المصدر: ISO 20715:2023 Tea — Classification of tea types

- **الشاي الأسود**: تشمل معالجته تحت ISO 20715: الذبول، ثم اللفّ أو السحق، ثم التهوية/الأكسدة، ثم التجفيف. وكلمة "التخمير" (fermentation) في تجارة الشاي تُستخدم غالبًا لهذه الخطوة المؤكسدة إنزيميًا، وهي **لا تعني بالضرورة تخمّرًا ميكروبيًا**.
  - المصادر: ISO 20715:2023 Tea — Classification of tea types؛ Fermentation: The Key Step in Processing of Black Tea

## توضيح مهم حول مصطلح "التخمير"
عند السؤال عمّا إذا كان الشاي "مخمَّرًا"، يجب توضيح أي عملية يُقصد:
- الشاي الأخضر: أكسدة قليلة أو معدومة عمدًا.
- الشاي الأسود: أكسدة إنزيمية بعد تمزيق الأوراق وتعريضها للهواء.
- الأولونغ: أكسدة جزئية.
- الشاي الداكن (dark tea): قد تتضمن مرحلة تكديس أو تخمّر لاحق منفصلة.
  - المصدر: Fermentation: The Key Step in Processing of Black Tea

## ملاحظة إضافية
- الصنف النباتي (cultivar) ونوع الشاي (نوع المنتج المصنّع) مفهومان مختلفان؛ فمعالجة صنف واحد بستّ طرق نموذجية أنتجت تراكيب كيميائية متباينة، لذا لا يحدّد الصنف وحده نوع الشاي النهائي أو رائحته.
  - المصدر: Impact of Six Typical Processing Methods on the Chemical Composition of Tea Leaves
- Orthodox وCTC هما أسلوبا تصنيع وليسا محور تصنيف أنواع الشاي الستة الأساسية؛ وCTC تعني السحق والتمزيق واللفّ وتُستخدم عادةً لتحضيرات قوية وأكياس الشاي.
  - المصدر: Tea Board India — Modalities and Scheme Guidelines

## حدود المعلومات
لم تُقدَّم في هذه الجولة أي بيانات عن أسعار أو مخزون أو طلبات، ولا يمكنني تقديمها دون استعلام مباشر. كما لا تتوفر معلومات موثّقة هنا عن النكهات أو الاستخدامات المحددة لكل نوع، فلا يمكن التحقق منها.

**人工复核：** 完成；阿拉伯文输入正确识别为绿茶/红茶制造区别，以阿拉伯文解释核心区别及红茶步骤，有相应英文片段。

耗时 20.847s；模型调用 3；Token 输入 5598 / 输出 1502。

最终支持点指标：`{"selected_ids": [65, 81, 64, 78, 79], "support_groups_hit": 2, "support_groups_total": 2, "support_group_coverage": 1.0, "all_available_support": true, "labelled_relevant_precision": 0.6}`。

查询与补检实际记录：

```json
[]
```

实际来源：

- [ISO 20715:2023 Tea — Classification of tea types](https://www.iso.org/obp/ui?_escaped_fragment_=iso%3Astd%3Aiso%3A20715%3Aed-1%3Av1%3Aen)
- [Fermentation: The Key Step in Processing of Black Tea](https://agris.fao.org/search/fr/records/6473b0a3542a3f9f03b31231)
- [Impact of Six Typical Processing Methods on the Chemical Composition of Tea Leaves](https://agris.fao.org/search/en/records/65dff5d763b8185d9cb04493)
- [Tea Board India — Modalities and Scheme Guidelines](https://www.teaboard.gov.in/pdf/schemes/Modalities_and_scheme_guidelines_12th_Plan.pdf)

### B · 查询改写

# الفرق بين تصنيع الشاي الأخضر والشاي الأسود

## الفرق الجوهري
الفرق الأساسي هو **الأكسدة الإنزيمية**:

- **الشاي الأخضر**: يُصنع بتطبيق الحرارة سريعًا على الأوراق الطازجة لتعطيل الإنزيمات، ثم قد تشمل الخطوات اللف أو التشكيل أو التقطيع، ثم التجفيف. **لا يُهوّى/يُؤكسد عمدًا** كما في عملية الشاي الأسود. تختلف طرق التسخين والأشكال حسب المنطقة والمنتج.
  - المصدر: *ISO 20715:2023 Tea — Classification of tea types*

- **الشاي الأسود**: في تصنيعه، يشير مصطلح "التخمير" (fermentation) في الصناعة إلى **الأكسدة الإنزيمية** بعد تمزيق الأوراق وتعريضها للهواء. وهو مختلف عن التخمير الميكروبي. ويُصنع الشاي الأخضر بأكسدة قليلة أو معدومة عمدًا، بينما يُؤكسد الشاي الأولونغ جزئيًا.
  - المصدر: *Fermentation: The Key Step in Processing of Black Tea*

## نقطة مهمة للتوضيح
عند السؤال عمّا إذا كان الشاي "مخمّرًا"، يجب توضيح أي عملية يُقصد: الأكسدة الإنزيمية أم التخمير الميكروبي.
  - المصدر: *Fermentation: The Key Step in Processing of Black Tea*

## ملاحظة إضافية
الصنف النباتي (cultivar) ونوع الشاي (أسود، أخضر، أولونغ، أبيض، أصفر، داكن) مفهومان مختلفان. معالجة نفس الصنف بست طرق نموذجية أنتجت تركيبات كيميائية متمايزة؛ لذا لا يحدد الصنف وحده نوع الشاي النهائي أو رائحته، بل المعالجة أيضًا مهمة.
  - المصدر: *Impact of Six Typical Processing Methods on the Chemical Composition of Tea Leaves*

## تنبيه
المصادر المتاحة لا تحدد سنة النشر لبعض المراجع. لم تُطلب في هذا السؤال تفاصيل عن منتجات أو أسعار أو مخزون، لذا لا تتضمن الإجابة بيانات تجارية.

**人工复核：** 完成；阿拉伯文答复正确解释加热灭酶与酶促氧化区别；没有补充64片段的完整红茶步骤。

耗时 18.714s；模型调用 4；Token 输入 6695 / 输出 1308。

最终支持点指标：`{"selected_ids": [65, 81, 68, 78, 79], "support_groups_hit": 2, "support_groups_total": 2, "support_group_coverage": 1.0, "all_available_support": true, "labelled_relevant_precision": 0.4}`。

查询与补检实际记录：

```json
[
  {
    "original_query": "اشرح الفرق بين تصنيع الشاي الأخضر والشاي الأسود.",
    "rewrite_status": [
      "translated"
    ],
    "rewrite_error_types": [],
    "rejected_variants": 0,
    "queries": [
      {
        "round": 0,
        "query": "اشرح الفرق بين تصنيع الشاي الأخضر والشاي الأسود.",
        "limit": 15,
        "hits": 15,
        "status": "success"
      },
      {
        "round": 0,
        "query": "Explain the difference between the manufacturing processes of green tea and black tea.",
        "limit": 5,
        "hits": 5,
        "status": "success"
      },
      {
        "round": 0,
        "query": "解释绿茶和红茶加工工艺的区别。",
        "limit": 5,
        "hits": 5,
        "status": "success"
      },
      {
        "round": 0,
        "query": "اشرح الفرق بين تصنيع الشاي الأخضر والشاي الأسود. | 绿茶 green tea 红茶 black tea 加工 processing",
        "limit": 5,
        "hits": 5,
        "status": "success"
      }
    ],
    "rerank_status": [
      "success"
    ],
    "retry": false,
    "retry_adopted": false,
    "retry_reasons": [],
    "selected_ids": [
      "65",
      "81",
      "68",
      "78",
      "79"
    ],
    "remaining_issues": [],
    "missing_subjects": []
  }
]
```

实际来源：

- [ISO 20715:2023 Tea — Classification of tea types](https://www.iso.org/obp/ui?_escaped_fragment_=iso%3Astd%3Aiso%3A20715%3Aed-1%3Av1%3Aen)
- [Fermentation: The Key Step in Processing of Black Tea](https://agris.fao.org/search/fr/records/6473b0a3542a3f9f03b31231)
- [Impact of Six Typical Processing Methods on the Chemical Composition of Tea Leaves](https://agris.fao.org/search/en/records/65dff5d763b8185d9cb04493)
- [Tea Board India — Modalities and Scheme Guidelines](https://www.teaboard.gov.in/pdf/schemes/Modalities_and_scheme_guidelines_12th_Plan.pdf)

## 05 · 中文双国习俗与资料缺口

**用户：** 请比较沙特阿拉伯与阿联酋的饮茶习惯。

预先固定目标：有依据介绍沙特；明确缺少阿联酋习惯资料，不以贸易/预测数据替代习惯。

### A · 单查询

根据本次可核验的资料，沙特阿拉伯与阿联酋的饮茶习惯对比如下：

**沙特阿拉伯**
- 待客礼仪中，通常是先上咖啡、后上茶；若场合包含午餐或晚餐，茶有时会在餐后供应。可加入薄荷、婆婆纳或其他芳香叶类。—《Drinks in Saudi Arabia, Saudipedia》，年份未标注
- 有一种“炭火茶”（ember tea）：在水壶中用炭火煮水和糖，再加入粗茶叶；这种风格与户外露营相关。—同上
- 上述为有记载的习俗，并非每个家庭都遵循的统一规则。—同上

**阿联酋**
- 本次检索到的证据中，没有关于阿联酋饮茶习惯、礼仪或冲泡方式的记载，因此无法就习惯层面与沙特进行对比。

**可补充的量化背景（仅历史预测，非实际消费量）**
- 2014年FAO中期展望曾估计：2013年沙特黑茶消费量30,350吨，并预测2023年为44,999吨；阿联酋2013年为40,000吨，预测2023年为63,394吨。—《Medium-term outlook for tea, 2014 FAO projection》，2014年发布
- 这些是当年的预测值，不是已核实的2023年实际消费量，也不能等同于进口量。

**说明**
- 检索到的UNESCO“çay”文化资料涉及阿塞拜疆和土耳其，与沙特、阿联酋无关，故不用于本次对比。
- 关于两国茶叶的风味、用途等属性，本次未配置相关数据，无法验证。

如需，我可以再帮你查阿联酋饮茶习惯的专门资料。

**人工复核：** 部分；有依据描述沙特、承认阿联酋习惯缺口；额外历史预测中将black tea误译为黑茶。

耗时 29.545s；模型调用 2；Token 输入 4521 / 输出 775。

最终支持点指标：`{"selected_ids": [59, 51, 58, 53, 57], "support_groups_hit": 1, "support_groups_total": 1, "support_group_coverage": 1.0, "all_available_support": true, "labelled_relevant_precision": 0.2}`。

查询与补检实际记录：

```json
[]
```

实际来源：

- [Drinks in Saudi Arabia, Saudipedia](https://saudipedia.com/en/drinks-in-saudi-arabia)
- [Medium-term outlook for tea, 2014 FAO projection](https://www.fao.org/fileadmin/templates/est/meetings/IGGtea21/14-Inf3-CurrentSituation.pdf)
- [Culture of Çay (tea), UNESCO Intangible Cultural Heritage](https://ich.unesco.org/en/RL/culture-of-cay-tea-a-symbol-of-identity-hospitality-and-social-interaction-01685?RL=01685)

### B · 查询改写

关于沙特阿拉伯与阿联酋饮茶习惯的比较，本次检索到的证据并不对称：沙特有较具体的饮茶习俗资料，阿联酋方面只找到贸易/消费预测类数据，没有找到直接描述其饮茶习惯的证据。以下按现有资料分别说明，并明确资料缺口。

**沙特阿拉伯的饮茶习惯（有习俗类证据）**
- 据 Saudipedia，咖啡之后上茶是沙特待客礼仪的一部分；若场合包含午餐或晚餐，茶有时会在餐后较晚时段提供。可加入薄荷、婆婆纳或其他芳香叶类。
- 同源资料提到一种“炭火茶”（ember tea）：在水壶中用炭火煮水和糖，再加入粗茶叶；这种风格与户外露营相关。
- 需注意：这些是已记录的习俗，并非每个家庭都适用的普遍规则。
- 来源：Drinks in Saudi Arabia, Saudipedia（年份未标注）。

**阿联酋的饮茶习惯**
- 本次检索未找到直接描述阿联酋饮茶习惯（如待客方式、常见茶类、冲泡方式）的证据，因此无法与沙特做习俗层面的比较。
- 仅有贸易与预测类数据可作背景参考：
  - 世界银行 WITS 引用 UN Comtrade 的 2023 年数据：阿联酋 HS 0902（茶，含调味茶）进口额约 2.2101 亿美元、重量 73,427.2 吨。这是总进口，且阿联酋是贸易与转口枢纽，进口量不能等同于本地消费量。
  - FAO 2014 年中期展望曾估计阿联酋 2013 年红茶消费量 40,000 吨，并预测 2023 年为 63,394 吨；该 2023 数值是旧预测，不是已核实的实际观测值。
- 来源：Tea imports by country, 2023 (HS 0902)，2023；Medium-term outlook for tea, 2014 FAO projection，2023。

**关于消费量的补充（沙特）**
- FAO 2014 年中期展望曾估计沙特 2013 年红茶消费量 30,350 吨，并预测 2023 年为 44,999 吨；同样属于历史预测，不是已核实的 2023 年实际消费量。
- 来源：Medium-term outlook for tea, 2014 FAO projection，2023。

**结论与资料缺口**
- 就现有证据，只能确认沙特有较明确的待客用茶与炭火茶习俗描述；阿联酋的饮茶习惯缺乏直接证据，无法可靠比较两者的具体饮茶方式。
- 进口量不能等同消费量；上述消费数字均为 2014 年的预测性资料，不宜当作当前实际值。
- 检索到的 UNESCO“çay”资料针对土耳其和阿塞拜疆，与沙特、阿联酋无关，不用于本次比较。

如果你希望，我可以再尝试补充检索阿联酋饮茶习俗方面的资料。

**人工复核：** 部分；明确指出两国证据不对称，未编造阿联酋习俗；补检后仍没有阿联酋直接证据，额外贸易/预测背景较长，引用年份标记存在2014/2023混用。

耗时 29.307s；模型调用 4；Token 输入 7150 / 输出 1637。

最终支持点指标：`{"selected_ids": [59, 51, 53, 35, 57], "support_groups_hit": 1, "support_groups_total": 1, "support_group_coverage": 1.0, "all_available_support": true, "labelled_relevant_precision": 0.2}`。

查询与补检实际记录：

```json
[
  {
    "original_query": "请比较沙特阿拉伯与阿联酋的饮茶习惯。",
    "rewrite_status": [
      "translated",
      "translated"
    ],
    "rewrite_error_types": [],
    "rejected_variants": 0,
    "queries": [
      {
        "round": 0,
        "query": "请比较沙特阿拉伯与阿联酋的饮茶习惯。",
        "limit": 15,
        "hits": 15,
        "status": "success"
      },
      {
        "round": 0,
        "query": "Please compare the tea drinking habits of Saudi Arabia and the United Arab Emirates.",
        "limit": 5,
        "hits": 5,
        "status": "success"
      },
      {
        "round": 0,
        "query": "请比较沙特阿拉伯与阿联酋的饮茶习惯。 | Saudi Arabia United Arab Emirates tea drinking customs",
        "limit": 5,
        "hits": 5,
        "status": "success"
      },
      {
        "round": 0,
        "query": "请比较沙特阿拉伯与阿联酋的饮茶习俗。",
        "limit": 5,
        "hits": 5,
        "status": "success"
      },
      {
        "round": 1,
        "query": "请比较沙特阿拉伯与阿联酋的饮茶习惯。 | 阿联酋 United Arab Emirates 饮茶习惯 tea drinking customs",
        "limit": 7,
        "hits": 7,
        "status": "success"
      },
      {
        "round": 1,
        "query": "请比较沙特阿拉伯与阿联酋的饮茶习俗与待客礼仪。",
        "limit": 8,
        "hits": 8,
        "status": "success"
      }
    ],
    "rerank_status": [
      "success",
      "success"
    ],
    "retry": true,
    "retry_adopted": true,
    "retry_reasons": [
      "subject_topic_gap"
    ],
    "selected_ids": [
      "59",
      "51",
      "53",
      "35",
      "57"
    ],
    "remaining_issues": [
      "subject_topic_gap"
    ],
    "missing_subjects": [
      "uae"
    ]
  }
]
```

实际来源：

- [Drinks in Saudi Arabia, Saudipedia](https://saudipedia.com/en/drinks-in-saudi-arabia)
- [Medium-term outlook for tea, 2014 FAO projection](https://www.fao.org/fileadmin/templates/est/meetings/IGGtea21/14-Inf3-CurrentSituation.pdf)
- [Tea imports by country, 2023 (HS 0902)](https://wits.worldbank.org/trade/comtrade/en/country/All/year/2023/tradeflow/Imports/partner/WLD/product/0902)
- [Culture of Çay (tea), UNESCO Intangible Cultural Heritage](https://ich.unesco.org/en/RL/culture-of-cay-tea-a-symbol-of-identity-hospitality-and-social-interaction-01685?RL=01685)

## 06 · 英文双国习俗与资料缺口

**用户：** Compare tea drinking customs in Saudi Arabia and the United Arab Emirates.

预先固定目标：有依据介绍沙特；明确缺少阿联酋习惯资料，不以贸易/预测数据替代习惯。

### A · 单查询

以下基于本次检索到的资料，比较沙特阿拉伯与阿联酋的饮茶习俗。需要说明：现有证据对沙特阿拉伯有习俗描述，对阿联酋主要是贸易/消费数据，缺少习俗细节，因此无法做完整的习俗对比。

**沙特阿拉伯**
- 待客礼仪：据 Saudipedia，沙特阿拉伯待客礼仪中先上咖啡、后上茶；若场合包含午餐或晚餐，茶有时在餐后供应。可加入薄荷、婆婆纳（speedwell）或其他香草叶。（来源：Drinks in Saudi Arabia, Saudipedia，年份未标注）
- 一种做法“ember tea”：在水壶中用余烬煮沸水和糖，再加入粗茶；这种风格与户外露营相关。（同上）
- 该来源强调这些是已记录的习俗，并非每个家庭都适用的普遍规则。（同上）

**阿联酋**
- 现有证据未提供阿联酋饮茶习俗（如待客顺序、加料、饮用场景）的描述，因此无法验证其具体习俗，也无法与沙特阿拉伯逐项对比。
- 可参考的市场数据（非习俗）：
  - 2023 年阿联酋 HS 0902（茶，含调味茶）进口额 2.21010 亿美元、重量 73,427.2 吨；这是总进口，因阿联酋是贸易与转口枢纽，不能等同于本地消费。（来源：Tea imports by country, 2023 (HS 0902)，2023）
  - 历史背景：FAO 2014 年中期展望估计阿联酋 2013 年红茶消费 40,000 吨，并预测 2023 年为 63,394 吨；该 2023 数值是旧预测，非已核实实际值。（来源：Medium-term outlook for tea, 2014 FAO projection，2023）

**沙特阿拉伯市场数据（供参考，非习俗）**
- 2023 年沙特阿拉伯 HS 0902 进口额 2.54806 亿美元；该摘要未提供数量。进口额不等于国内消费或零售市场价值。（来源：Tea imports by country, 2023 (HS 0902)，2023）
- 历史背景：FAO 2014 年展望估计沙特阿拉伯 2013 年红茶消费 30,350 吨，预测 2023 年为 44,999 吨；属历史预测，非实测值。（来源：Medium-term outlook for tea, 2014 FAO projection，2023）

**结论**
- 就习俗而言，目前只能确认沙特阿拉伯的咖啡—茶待客顺序、可加薄荷/香草、以及露营式 ember tea；阿联酋的饮茶习俗在本次证据中缺失，无法可靠比较。
- 进口量不能等同消费量，尤其阿联酋存在转口贸易。

如需更完整的习俗对比，请补充阿联酋饮茶习俗相关的可核实资料。

**人工复核：** 部分；正确介绍沙特并承认缺少阿联酋习俗，明确历史预测不是实测；附加贸易数据冗长，引用年份标记有混用。

耗时 22.73s；模型调用 2；Token 输入 4735 / 输出 1290。

最终支持点指标：`{"selected_ids": [59, 35, 53, 51, 34], "support_groups_hit": 1, "support_groups_total": 1, "support_group_coverage": 1.0, "all_available_support": true, "labelled_relevant_precision": 0.2}`。

查询与补检实际记录：

```json
[]
```

实际来源：

- [Drinks in Saudi Arabia, Saudipedia](https://saudipedia.com/en/drinks-in-saudi-arabia)
- [Tea imports by country, 2023 (HS 0902)](https://wits.worldbank.org/trade/comtrade/en/country/All/year/2023/tradeflow/Imports/partner/WLD/product/0902)
- [Medium-term outlook for tea, 2014 FAO projection](https://www.fao.org/fileadmin/templates/est/meetings/IGGtea21/14-Inf3-CurrentSituation.pdf)

### B · 查询改写

**沙特阿拉伯与阿联酋饮茶习俗对比**

**沙特阿拉伯**
- 据 Saudipedia 记载，沙特待客礼仪中通常先上咖啡、后上茶；若场合包含午餐或晚餐，茶有时会在餐后供应。可加入薄荷、婆婆纳或其他芳香叶片。其“炭火茶（ember tea）”描述为：在水壶中用炭火煮沸水和糖，再加入粗茶叶，这种风格与户外露营相关。以上为有据可查的习俗，并非每个家庭都遵循的统一规则。（来源：Drinks in Saudi Arabia, Saudipedia，年份未标注）

**阿拉伯联合酋长国**
- 本次检索**未找到**关于阿联酋饮茶习俗的直接证据，因此无法就饮用方式、待客礼仪或常见风味作出比较。资料缺口如实说明，不据此推断。

**贸易数据（仅作背景，不等于消费量）**
- 沙特：2023 年 HS 0902（茶，含调味茶）进口额 2.54806 亿美元；该摘要未提供进口数量。进口额不等于国内消费量或零售市场价值。（来源：Tea imports by country, 2023 (HS 0902)，2023）
- 阿联酋：2023 年 HS 0902 进口额 2.21010 亿美元，重量 73,427.2 吨。阿联酋作为贸易与转口枢纽，进口量不应解读为本地消费量。（来源：Tea imports by country, 2023 (HS 0902)，2023）
- 历史预测（非实测）：FAO 2014 年中期展望曾估计沙特 2013 年红茶消费 30,350 吨、预测 2023 年 44,999 吨；阿联酋 2013 年 40,000 吨、预测 2023 年 63,394 吨。这些是旧预测，不是已核实的实际观测值。（来源：Medium-term outlook for tea, 2014 FAO projection，2023）

**结论**：目前只能确认沙特的待客与炭火茶习俗；阿联酋的饮茶习俗缺乏本次可验证证据，无法完成习俗层面的对比。

**人工复核：** 部分；同样守住资料边界，未完成阿联酋习俗比较；引用年份标记有混用，附加贸易信息并不回答习俗。

耗时 27.677s；模型调用 4；Token 输入 6958 / 输出 1307。

最终支持点指标：`{"selected_ids": [59, 51, 53, 35, 34], "support_groups_hit": 1, "support_groups_total": 1, "support_group_coverage": 1.0, "all_available_support": true, "labelled_relevant_precision": 0.2}`。

查询与补检实际记录：

```json
[
  {
    "original_query": "Compare tea drinking customs in Saudi Arabia and the United Arab Emirates.",
    "rewrite_status": [
      "translated",
      "translated"
    ],
    "rewrite_error_types": [],
    "rejected_variants": 0,
    "queries": [
      {
        "round": 0,
        "query": "Compare tea drinking customs in Saudi Arabia and the United Arab Emirates.",
        "limit": 15,
        "hits": 15,
        "status": "success"
      },
      {
        "round": 0,
        "query": "比较沙特阿拉伯和阿联酋的饮茶习俗。",
        "limit": 5,
        "hits": 5,
        "status": "success"
      },
      {
        "round": 0,
        "query": "Compare tea drinking customs in Saudi Arabia and the United Arab Emirates. | 沙特阿拉伯 阿联酋 饮茶习惯",
        "limit": 5,
        "hits": 5,
        "status": "success"
      },
      {
        "round": 0,
        "query": "比较沙特阿拉伯与阿联酋的饮茶习惯和待客礼仪。",
        "limit": 5,
        "hits": 5,
        "status": "success"
      },
      {
        "round": 1,
        "query": "Compare tea drinking customs in Saudi Arabia and the United Arab Emirates. | 阿联酋 United Arab Emirates 饮茶习惯 tea drinking customs",
        "limit": 7,
        "hits": 7,
        "status": "success"
      },
      {
        "round": 1,
        "query": "比较沙特阿拉伯与阿联酋的饮茶传统和待客礼仪。",
        "limit": 8,
        "hits": 8,
        "status": "success"
      }
    ],
    "rerank_status": [
      "success",
      "success"
    ],
    "retry": true,
    "retry_adopted": true,
    "retry_reasons": [
      "subject_topic_gap"
    ],
    "selected_ids": [
      "59",
      "51",
      "53",
      "35",
      "34"
    ],
    "remaining_issues": [
      "subject_topic_gap"
    ],
    "missing_subjects": [
      "uae"
    ]
  }
]
```

实际来源：

- [Drinks in Saudi Arabia, Saudipedia](https://saudipedia.com/en/drinks-in-saudi-arabia)
- [Medium-term outlook for tea, 2014 FAO projection](https://www.fao.org/fileadmin/templates/est/meetings/IGGtea21/14-Inf3-CurrentSituation.pdf)
- [Tea imports by country, 2023 (HS 0902)](https://wits.worldbank.org/trade/comtrade/en/country/All/year/2023/tradeflow/Imports/partner/WLD/product/0902)

## 07 · 中英缩写国家习俗

**用户：** 请比较Saudi Arabia和UAE的饮茶习惯与待客礼仪。

预先固定目标：理解国名与缩写；有依据介绍沙特，承认阿联酋习惯资料缺口。

### A · 单查询

关于沙特阿拉伯与阿联酋的饮茶习惯与待客礼仪比较，本次检索到的证据情况如下：

**沙特阿拉伯（有部分证据）**
- 据 Saudipedia 记载，沙特待客礼仪中通常是先上咖啡、后上茶；若场合包含午餐或晚餐，茶有时会在餐后较晚时段提供。茶中可能加入薄荷、婆婆纳或其他芳香叶片。其“余烬茶”（ember tea）描述为：在水壶中用余烬煮沸水和糖，再加入粗茶；这种风格与户外露营相关。该来源也说明这些是记录下来的习俗，并非每个家庭都适用的普遍规则。（来源：Drinks in Saudi Arabia, Saudipedia，年份未标注）

**阿联酋（无直接证据）**
- 本次工具结果中没有检索到关于阿联酋饮茶习惯或待客礼仪的证据，因此无法对阿联酋作同等比较，不编造相关内容。

**需要说明的边界**
- 检索到的 UNESCO“çay 茶文化”资料涉及土耳其和阿塞拜疆，不是沙特或阿联酋，不能用于本次比较。
- FAO 2014 年中期展望中提到的沙特、阿联酋黑茶数据属于历史预测（如沙特 2013 年 30,350 吨、2023 年预测 44,999 吨；阿联酋 2013 年 40,000 吨、2023 年预测 63,394 吨），是旧预测而非实测消费量，且进口/消费数据不能等同于饮茶习惯或待客礼仪，故不用于礼仪比较。

**结论**：目前只能依据证据介绍沙特的饮茶与待客习俗；阿联酋方面证据缺失，无法完成两国对比。如需阿联酋部分，建议补充可验证来源后再作比较。

**人工复核：** 部分；正确理解Saudi Arabia/UAE，承认阿联酋无直接习俗证据；附加预测将black tea误译为黑茶。

耗时 20.21s；模型调用 2；Token 输入 4571 / 输出 826。

最终支持点指标：`{"selected_ids": [59, 51, 57, 53, 58], "support_groups_hit": 1, "support_groups_total": 1, "support_group_coverage": 1.0, "all_available_support": true, "labelled_relevant_precision": 0.2}`。

查询与补检实际记录：

```json
[]
```

实际来源：

- [Drinks in Saudi Arabia, Saudipedia](https://saudipedia.com/en/drinks-in-saudi-arabia)
- [Medium-term outlook for tea, 2014 FAO projection](https://www.fao.org/fileadmin/templates/est/meetings/IGGtea21/14-Inf3-CurrentSituation.pdf)
- [Culture of Çay (tea), UNESCO Intangible Cultural Heritage](https://ich.unesco.org/en/RL/culture-of-cay-tea-a-symbol-of-identity-hospitality-and-social-interaction-01685?RL=01685)

### B · 查询改写

**沙特阿拉伯与阿联酋饮茶习惯及待客礼仪比较**

**一、沙特阿拉伯（有直接证据）**

据 Saudipedia《Drinks in Saudi Arabia》记载：
- **待客顺序**：咖啡之后上茶，是沙特待客礼仪的一部分；若场合包含午餐或晚餐，茶有时会在餐后较晚时段供应。
- **风味添加**：可加入薄荷、婆婆纳（speedwell）或其他芳香叶片。
- **炭火茶（ember tea）**：将水和糖在壶中置于炭火上煮沸，再加入粗茶叶；这种风格与户外露营相关。
- 该来源说明这些是**有记载的习俗，并非每个家庭都适用的普遍规则**。

**二、阿联酋**

本次检索**未找到**同时覆盖阿联酋饮茶习惯与待客礼仪的直接证据。因此无法对阿联酋的饮茶习惯或待客礼仪作出可靠描述，也不据此推断。

**三、可作背景参考（非沙特/阿联酋）**

UNESCO 2022年列入非遗名录的“çay 茶文化”涉及**土耳其与阿塞拜疆**：茶被视为与待客、维系关系和重要场合相关的社会实践，主要饮用红茶，趁热现泡，常用梨形小杯配甜食、糖、柠檬、果酱或干果；阿塞拜疆部分地区会加肉桂、姜、百里香等香料或香草，做法因社区而异。此为背景资料，**不能直接套用于沙特或阿联酋**。

**四、消费量数据（历史预测，非实际观测）**

FAO 2014年中期展望（历史资料）：
- 沙特阿拉伯：2013年红茶消费估计 30,350 吨，预测2023年为 44,999 吨。
- 阿联酋：2013年红茶消费估计 40,000 吨，预测2023年为 63,394 吨。

以上均为**2014年的旧预测值，不是已核实的2023年实际消费量**；进口量也不能等同于消费量。

**结论**：目前仅能就沙特的饮茶与待客习俗提供有据可查的描述；阿联酋方面资料缺口明确，无法完成对等比较。如需阿联酋部分，建议补充相关来源后再作对照。

**人工复核：** 部分；理解缩写且说明资料缺口，附加数据使用红茶译名；仍用较长篇幅介绍非目标国家文化和消费预测。

耗时 28.328s；模型调用 4；Token 输入 6958 / 输出 1389。

最终支持点指标：`{"selected_ids": [59, 57, 51, 53, 58], "support_groups_hit": 1, "support_groups_total": 1, "support_group_coverage": 1.0, "all_available_support": true, "labelled_relevant_precision": 0.2}`。

查询与补检实际记录：

```json
[
  {
    "original_query": "请比较Saudi Arabia和UAE的饮茶习惯与待客礼仪。",
    "rewrite_status": [
      "translated",
      "translated"
    ],
    "rewrite_error_types": [],
    "rejected_variants": 0,
    "queries": [
      {
        "round": 0,
        "query": "请比较Saudi Arabia和UAE的饮茶习惯与待客礼仪。",
        "limit": 15,
        "hits": 15,
        "status": "success"
      },
      {
        "round": 0,
        "query": "Please compare the tea drinking habits and hospitality etiquette of Saudi Arabia and the UAE.",
        "limit": 5,
        "hits": 5,
        "status": "success"
      },
      {
        "round": 0,
        "query": "请比较沙特阿拉伯和阿联酋的饮茶习惯与待客礼仪。",
        "limit": 5,
        "hits": 5,
        "status": "success"
      },
      {
        "round": 0,
        "query": "请比较Saudi Arabia和UAE的饮茶习惯与待客礼仪。 | 沙特阿拉伯 阿联酋 United Arab Emirates tea drinking customs",
        "limit": 5,
        "hits": 5,
        "status": "success"
      },
      {
        "round": 1,
        "query": "请比较Saudi Arabia和UAE的饮茶习惯与待客礼仪。 | 阿联酋 United Arab Emirates 饮茶习惯 tea drinking customs",
        "limit": 7,
        "hits": 7,
        "status": "success"
      },
      {
        "round": 1,
        "query": "Please compare the tea drinking habits and hospitality etiquette of Saudi Arabia and the United Arab Emirates.",
        "limit": 8,
        "hits": 8,
        "status": "success"
      }
    ],
    "rerank_status": [
      "success",
      "success"
    ],
    "retry": true,
    "retry_adopted": true,
    "retry_reasons": [
      "subject_topic_gap"
    ],
    "selected_ids": [
      "59",
      "57",
      "51",
      "53",
      "58"
    ],
    "remaining_issues": [
      "subject_topic_gap"
    ],
    "missing_subjects": [
      "uae"
    ]
  }
]
```

实际来源：

- [Drinks in Saudi Arabia, Saudipedia](https://saudipedia.com/en/drinks-in-saudi-arabia)
- [Culture of Çay (tea), UNESCO Intangible Cultural Heritage](https://ich.unesco.org/en/RL/culture-of-cay-tea-a-symbol-of-identity-hospitality-and-social-interaction-01685?RL=01685)
- [Medium-term outlook for tea, 2014 FAO projection](https://www.fao.org/fileadmin/templates/est/meetings/IGGtea21/14-Inf3-CurrentSituation.pdf)

## 08 · 双国均有资料的习俗比较

**用户：** 请比较约旦和沙特的待客饮茶习俗。

预先固定目标：分别以约旦日常聚会/芳香植物和沙特待客/炭火茶资料进行比较，不能拿消费预测替代。

### A · 单查询

根据本次检索到的资料，约旦和沙特的待客饮茶习俗可作如下比较：

**约旦**
- 茶是日常社会与文化生活的组成部分，常见于家庭拜访和聚会场合（来源：Tea's place in Jordanian popular memory and culture, Petra News Agency，年份未标注）。
- 常与芳香植物一起冲泡，当地研究者提到的例子包括薄荷、茴香和鼠尾草；城市、乡村和贝都因社区做法有差异，这些风味应视为常见例子，而非单一全国配方（同上）。

**沙特阿拉伯**
- 待客礼仪中常是先上咖啡、后上茶；若场合包含午餐或晚餐，茶有时在餐后较晚时段供应（来源：Drinks in Saudi Arabia, Saudipedia，年份未标注）。
- 可加入薄荷、婆婆纳或其他芳香叶子（同上）。
- 有一种“余烬茶”（ember tea）：在水壶中用余烬煮沸水和糖，再加入粗茶叶，这种风格与户外露营相关（同上）。
- 上述均为有记载的习俗，并非每个家庭都适用的普遍规则（同上）。

**简要对比**
- 共同点：两国都把茶用于待客和社交聚会，且都常搭配芳香植物。
- 差异：沙特资料明确描述了“咖啡在前、茶在后”的待客顺序，以及户外露营式的余烬茶；约旦资料更强调茶在日常家庭拜访和聚会中的普遍性，以及城乡与贝都因社区之间的做法差异。

**说明**
- 以上仅为文化习俗比较，不涉及具体商品推荐或价格库存。
- 检索到的资料未标注具体年份；另有 UNESCO 关于土耳其和阿塞拜疆“çay 文化”的资料，以及 FAO 2014 年对约旦红茶消费的预测，均与本次约旦—沙特待客习俗比较无直接关系，故未纳入。
- 关于两国待客用茶的具体茶叶品类、冲泡比例等更细属性，本次资料未提供，无法验证。

**人工复核：** 完成；分别使用59/60片段比较沙特待客顺序和约旦日常聚会/香草习惯，没有把其他国家文化套用到目标国家。

耗时 20.798s；模型调用 2；Token 输入 6380 / 输出 894。

最终支持点指标：`{"selected_ids": [59, 60, 57, 58, 55], "support_groups_hit": 2, "support_groups_total": 2, "support_group_coverage": 1.0, "all_available_support": true, "labelled_relevant_precision": 0.4}`。

查询与补检实际记录：

```json
[]
```

实际来源：

- [Drinks in Saudi Arabia, Saudipedia](https://saudipedia.com/en/drinks-in-saudi-arabia)
- [Tea's place in Jordanian popular memory and culture, Petra News Agency](https://petra.gov.jo/index.php/ar/news/%D8%A7%D9%84%D9%8A%D9%88%D9%85-%D8%A7%D9%84%D8%B9%D8%A7%D9%84%D9%85%D9%8A-%D9%84%D9%84%D8%B4%D8%A7%D9%8A-%D9%85%D8%B4%D8%B1%D9%88%D8%A8-%D9%8A%D8%AE%D8%AA%D8%B2%D9%84-%D8%A7%D9%84%D8%B0%D8%A7%D9%83%D8%B1%D8%A9-%D8%A7%D9%84%D8%B4%D8%B9%D8%A8%D9%8A%D8%A9-%D9%88%D9%8A%D8%AD%D8%A7%D9%81%D8%B8-%D8%B9%D9%84%D9%89-%D8%AD%D8%B6%D9%88%D8%B1%D9%87-%D9%81%D9%8A-%D8%A7%D9%84%D8%AB%D9%82%D8%A7%D9%81%D8%A9-%D8%A7%D9%84%D8%A3%D8%B1%D8%AF%D9%86%D9%8A%D8%A9)
- [Culture of Çay (tea), UNESCO Intangible Cultural Heritage](https://ich.unesco.org/en/RL/culture-of-cay-tea-a-symbol-of-identity-hospitality-and-social-interaction-01685?RL=01685)
- [Medium-term outlook for tea, 2014 FAO projection](https://www.fao.org/fileadmin/templates/est/meetings/IGGtea21/14-Inf3-CurrentSituation.pdf)

### B · 查询改写

以下比较仅依据本次检索到的资料，且这些资料描述的是有记录的习俗，并非每个家庭都适用的统一规则。

**约旦**
- 据约旦通讯社 Petra 报道，约旦文化部遗产主管将茶描述为日常社会与文化生活的组成部分，包括家庭拜访和聚会。
- 报道提到茶常与芳香植物一起冲泡，当地研究者举出的例子包括薄荷、茴香和鼠尾草。
- 报道指出城市、乡村和贝都因社区之间存在差异，因此这些风味应视为常见例子，而非单一的国家配方。
- 来源：《Tea's place in Jordanian popular memory and culture, Petra News Agency》，年份未标注。

**沙特阿拉伯**
- 据 Saudipedia 描述，咖啡之后上茶是沙特待客礼仪的一部分；当场合包含午餐或晚餐时，茶有时会在稍后奉上。
- 可加入薄荷、婆婆纳（speedwell）或其他芳香叶子。
- 该来源描述的“余烬茶”（ember tea）做法是：在水壶中于余烬上煮沸水和糖，然后加入粗茶；这种风格与户外露营相关。
- 来源：《Drinks in Saudi Arabia, Saudipedia》，年份未标注。

**可比之处**
- 两者都把茶与待客、社交聚会联系起来。
- 两者都常见在茶中加入芳香植物：约旦例子有薄荷、茴香、鼠尾草；沙特例子有薄荷、婆婆纳等。
- 差异方面：沙特资料明确把茶放在“咖啡之后”的待客顺序中，并提到含餐场合茶可能稍后上；约旦资料更强调茶在日常家庭拜访与聚会中的普遍存在，以及城乡和贝都因社区之间的做法差异。

**需要说明的限制**
- 上述两份资料均未标注年份，无法据此判断习俗的时间范围。
- 检索到的 FAO 资料只有 2014 年对约旦和沙特黑茶消费量的中期预测（约旦 2013 年 5,327 吨、预测 2023 年 5,886 吨；沙特 2013 年 30,350 吨、预测 2023 年 44,999 吨），这是历史预测而非实测消费量，也不能等同于待客习俗，故不用于习俗比较。
- 检索到的 UNESCO 资料关于土耳其和阿塞拜疆的 çay 文化，与约旦、沙特无关，不纳入比较。
- 除上述内容外，本次未检索到更多关于两国待客饮茶细节（如具体奉茶顺序、杯具、次数等）的证据，无法进一步验证。

**人工复核：** 完成；核心习俗比较有59/60片段支持；附加预测说明误将black tea译为黑茶，说明术语规范未覆盖最终生成。

耗时 18.714s；模型调用 3；Token 输入 7708 / 输出 1291。

最终支持点指标：`{"selected_ids": [59, 60, 55, 51, 57], "support_groups_hit": 2, "support_groups_total": 2, "support_group_coverage": 1.0, "all_available_support": true, "labelled_relevant_precision": 0.4}`。

查询与补检实际记录：

```json
[
  {
    "original_query": "请比较约旦和沙特的待客饮茶习俗。",
    "rewrite_status": [
      "translated"
    ],
    "rewrite_error_types": [],
    "rejected_variants": 0,
    "queries": [
      {
        "round": 0,
        "query": "请比较约旦和沙特的待客饮茶习俗。",
        "limit": 15,
        "hits": 15,
        "status": "success"
      },
      {
        "round": 0,
        "query": "Please compare the tea-drinking customs for hosting guests in Jordan and Saudi Arabia.",
        "limit": 5,
        "hits": 5,
        "status": "success"
      },
      {
        "round": 0,
        "query": "请比较约旦和沙特阿拉伯的待客饮茶习俗。",
        "limit": 5,
        "hits": 5,
        "status": "success"
      },
      {
        "round": 0,
        "query": "请比较约旦和沙特的待客饮茶习俗。 | 沙特阿拉伯 Saudi Arabia Jordan 饮茶习惯 tea drinking customs",
        "limit": 5,
        "hits": 5,
        "status": "success"
      }
    ],
    "rerank_status": [
      "success"
    ],
    "retry": false,
    "retry_adopted": false,
    "retry_reasons": [],
    "selected_ids": [
      "59",
      "60",
      "55",
      "51",
      "57"
    ],
    "remaining_issues": [],
    "missing_subjects": []
  }
]
```

实际来源：

- [Drinks in Saudi Arabia, Saudipedia](https://saudipedia.com/en/drinks-in-saudi-arabia)
- [Tea's place in Jordanian popular memory and culture, Petra News Agency](https://petra.gov.jo/index.php/ar/news/%D8%A7%D9%84%D9%8A%D9%88%D9%85-%D8%A7%D9%84%D8%B9%D8%A7%D9%84%D9%85%D9%8A-%D9%84%D9%84%D8%B4%D8%A7%D9%8A-%D9%85%D8%B4%D8%B1%D9%88%D8%A8-%D9%8A%D8%AE%D8%AA%D8%B2%D9%84-%D8%A7%D9%84%D8%B0%D8%A7%D9%83%D8%B1%D8%A9-%D8%A7%D9%84%D8%B4%D8%B9%D8%A8%D9%8A%D8%A9-%D9%88%D9%8A%D8%AD%D8%A7%D9%81%D8%B8-%D8%B9%D9%84%D9%89-%D8%AD%D8%B6%D9%88%D8%B1%D9%87-%D9%81%D9%8A-%D8%A7%D9%84%D8%AB%D9%82%D8%A7%D9%81%D8%A9-%D8%A7%D9%84%D8%A3%D8%B1%D8%AF%D9%86%D9%8A%D8%A9)
- [Medium-term outlook for tea, 2014 FAO projection](https://www.fao.org/fileadmin/templates/est/meetings/IGGtea21/14-Inf3-CurrentSituation.pdf)
- [Culture of Çay (tea), UNESCO Intangible Cultural Heritage](https://ich.unesco.org/en/RL/culture-of-cay-tea-a-symbol-of-identity-hospitality-and-social-interaction-01685?RL=01685)

## 09 · 发酵术语区别

**用户：** 解释红茶的发酵与黑茶的后发酵有什么区别。

预先固定目标：区分红茶酶促氧化与黑茶渥堆/后发酵，不能将黑茶和红茶混为一类。

### A · 单查询

**红茶“发酵”与黑茶“后发酵”的区别**

**1. 红茶“发酵”的本质：酶促氧化**
- 在红茶制造中，行业用语“发酵”（fermentation）通常指茶叶细胞破损并接触空气后发生的**酶促氧化**（enzymatic oxidation），与微生物发酵不同。
- 红茶加工步骤一般包括萎凋、揉捻、发酵（氧化）、干燥。
- 来源：《Fermentation: The Key Step in Processing of Black Tea》（年份未标注）；《Processing and brewing of Gilan black tea, Journal of Food Science and Technology》（年份未标注）。

**2. 黑茶“后发酵”的本质：渥堆发酵**
- 黑茶（dark tea）加工在 ISO 20715 中包括：杀青、揉捻、**渥堆发酵**、干燥。
- 渥堆阶段使黑茶区别于红茶制造中常被称为“发酵”的酶促氧化，属于**后发酵**工艺。
- 来源：《ISO 20715:2023 Tea — Classification of tea types》。

**3. 核心区别**
- 红茶：酶促氧化，靠茶叶自身酶与空气接触作用。
- 黑茶：渥堆后发酵，是独立于酶促氧化的加工阶段。
- 两者都常被口语称为“发酵”，但机制不同；被问“是否发酵”时，需先确认指哪一种过程。
- 来源：《Fermentation: The Key Step in Processing of Black Tea》；《ISO 20715:2023 Tea — Classification of tea types》。

**4. 补充说明**
- 黑茶产品与各地制法有差异，不宜把所有黑茶视为同一配方。
- 来源：《ISO 20715:2023 Tea — Classification of tea types》。

**5. 无法验证的部分**
- 关于红茶与黑茶在具体风味、健康功效上的差异，本次工具证据未提供，无法验证，不作展开。

**来源汇总**
- 《Fermentation: The Key Step in Processing of Black Tea》（年份未标注）
- 《ISO 20715:2023 Tea — Classification of tea types》
- 《Processing and brewing of Gilan black tea, Journal of Food Science and Technology》（年份未标注）

**人工复核：** 完成；结合81/69片段区分红茶酶促氧化与黑茶渥堆后发酵，黑茶加工步骤有直接证据。

耗时 22.169s；模型调用 2；Token 输入 4756 / 输出 998。

最终支持点指标：`{"selected_ids": [81, 65, 69, 62, 78], "support_groups_hit": 2, "support_groups_total": 2, "support_group_coverage": 1.0, "all_available_support": true, "labelled_relevant_precision": 0.4}`。

查询与补检实际记录：

```json
[]
```

实际来源：

- [Fermentation: The Key Step in Processing of Black Tea](https://agris.fao.org/search/fr/records/6473b0a3542a3f9f03b31231)
- [ISO 20715:2023 Tea — Classification of tea types](https://www.iso.org/obp/ui?_escaped_fragment_=iso%3Astd%3Aiso%3A20715%3Aed-1%3Av1%3Aen)
- [Processing and brewing of Gilan black tea, Journal of Food Science and Technology](https://fsct.modares.ac.ir/files/fsct/user_files_749497/re1farahmand-A-10-20521-12-52bc60a.pdf)
- [Impact of Six Typical Processing Methods on the Chemical Composition of Tea Leaves](https://agris.fao.org/search/en/records/65dff5d763b8185d9cb04493)

### B · 查询改写

红茶“发酵”和黑茶“后发酵”不是同一种过程，主要区别如下：

**红茶：酶促氧化（常被行业称为“发酵”）**
- 红茶加工中的“fermentation（发酵）”是行业用语，指茶叶细胞破损、接触空气后发生的**酶促氧化**，并不等同于微生物发酵。
- ISO 20715:2023 将红茶加工概括为：萎凋、揉捻或切碎、通气/氧化、干燥；其中“发酵”常指这个酶驱动的氧化步骤，因此红茶也被描述为“氧化茶”。
- 来源：ISO 20715:2023 Tea — Classification of tea types；Fermentation: The Key Step in Processing of Black Tea。

**黑茶：后发酵（可能涉及微生物参与）**
- 黑茶可能包含单独的“堆积”或“后发酵”阶段，这与红茶那种酶促氧化是不同概念。
- 现有证据只说明黑茶可能涉及后发酵阶段，并提醒“发酵”一词容易混淆；未检索到足够证据展开黑茶后发酵的具体微生物种类、温度时长等细节，因此这些无法验证。
- 来源：Fermentation: The Key Step in Processing of Black Tea。

**一句话区分**
- 红茶：主要是**茶叶自身酶引起的氧化**，行业俗称“发酵”。
- 黑茶：是**后发酵**，可能涉及微生物作用，属于另一类加工阶段。

如果你愿意，我也可以继续按“氧化程度”把绿茶、乌龙茶、红茶、黑茶放在一起对比。

**人工复核：** 完成；核心区分正确；没有召回69的黑茶专段，回答补充黑茶可能有微生物参与，但当前返回的81等片段没有直接陈述这一点，存在证据外补充。

耗时 31.07s；模型调用 3；Token 输入 5831 / 输出 831。

最终支持点指标：`{"selected_ids": [81, 65, 64, 78, 79], "support_groups_hit": 2, "support_groups_total": 2, "support_group_coverage": 1.0, "all_available_support": true, "labelled_relevant_precision": 0.4}`。

查询与补检实际记录：

```json
[
  {
    "original_query": "解释红茶的发酵与黑茶的后发酵有什么区别。",
    "rewrite_status": [
      "translated"
    ],
    "rewrite_error_types": [],
    "rejected_variants": 0,
    "queries": [
      {
        "round": 0,
        "query": "解释红茶的发酵与黑茶的后发酵有什么区别。",
        "limit": 15,
        "hits": 15,
        "status": "success"
      },
      {
        "round": 0,
        "query": "Explain the difference between the fermentation of black tea and the post-fermentation of dark tea.",
        "limit": 5,
        "hits": 5,
        "status": "success"
      },
      {
        "round": 0,
        "query": "解释红茶的发酵与黑茶的后发酵有什么区别。 | black tea dark tea fermentation",
        "limit": 5,
        "hits": 5,
        "status": "success"
      },
      {
        "round": 0,
        "query": "红茶发酵与黑茶后发酵的区别是什么",
        "limit": 5,
        "hits": 5,
        "status": "success"
      }
    ],
    "rerank_status": [
      "success"
    ],
    "retry": false,
    "retry_adopted": false,
    "retry_reasons": [],
    "selected_ids": [
      "81",
      "65",
      "64",
      "78",
      "79"
    ],
    "remaining_issues": [],
    "missing_subjects": []
  }
]
```

实际来源：

- [Fermentation: The Key Step in Processing of Black Tea](https://agris.fao.org/search/fr/records/6473b0a3542a3f9f03b31231)
- [ISO 20715:2023 Tea — Classification of tea types](https://www.iso.org/obp/ui?_escaped_fragment_=iso%3Astd%3Aiso%3A20715%3Aed-1%3Av1%3Aen)
- [Impact of Six Typical Processing Methods on the Chemical Composition of Tea Leaves](https://agris.fao.org/search/en/records/65dff5d763b8185d9cb04493)
- [Tea Board India — Modalities and Scheme Guidelines](https://www.teaboard.gov.in/pdf/schemes/Modalities_and_scheme_guidelines_12th_Plan.pdf)

## 10 · 拼音和英语别名

**用户：** Explain hongcha versus heicha: is black tea the same as dark tea?

预先固定目标：明确hongcha=红茶=black tea，heicha=黑茶=dark tea，二者不同。

### A · 单查询

**红茶（hongcha）与黑茶（heicha）不是同一种茶。**

- **英文命名容易混淆**：在中文茶类里，hongcha 在英文中通常叫 black tea（红茶），尽管冲泡出的茶汤常偏红。这是翻译惯例，并不表示 hongcha 与中文的 heicha（英文常译 dark tea，黑茶）是同一种产品。若用户只说“black tea”，需先确认其指哪种加工传统或产地，因为英文命名在不同市场有歧义。（来源：Typology of Processed Tea，年份未标注）

- **加工上的关键区别**：红茶加工按 ISO 20715 包括萎凋、揉捻或切碎、通气/氧化、干燥；行业里说的“发酵”多指叶片破损接触空气后的酶促氧化，不一定指微生物发酵，所以红茶被描述为氧化茶。黑茶则可能涉及单独的渥堆或后发酵阶段。问“是否发酵”时，需先明确指哪种过程。（来源：ISO 20715:2023 Tea — Classification of tea types；Fermentation: The Key Step in Processing of Black Tea，年份未标注）

- **概念区分**：茶树品种与茶类是两个概念。品种指栽培选育的植株；红茶、绿茶、乌龙、白茶、黄茶、黑茶指加工后的产品类型。同一品种用六种典型工艺加工可产生不同的化学成分特征，因此品种本身不决定成品茶类或香气，加工同样重要。（来源：Impact of Six Typical Processing Methods on the Chemical Composition of Tea Leaves，年份未标注）

**结论**：hongcha（红茶）与 heicha（黑茶）是不同茶类，英文 black tea 通常对应 hongcha，dark tea 通常对应 heicha，二者不能等同。

如需进一步区分，请告诉我你指的是哪种具体茶品或产地，我可以据此说明。

**人工复核：** 完成；正确说明hongcha/红茶/black tea与heicha/黑茶/dark tea不同，76提供直接术语依据。

耗时 19.952s；模型调用 2；Token 输入 4658 / 输出 845。

最终支持点指标：`{"selected_ids": [76, 65, 81, 78, 64], "support_groups_hit": 1, "support_groups_total": 1, "support_group_coverage": 1.0, "all_available_support": true, "labelled_relevant_precision": 0.6}`。

查询与补检实际记录：

```json
[]
```

实际来源：

- [Typology of Processed Tea](https://agris.fao.org/search/zh/records/68cbbca2f61e5b80b5e93a95)
- [ISO 20715:2023 Tea — Classification of tea types](https://www.iso.org/obp/ui?_escaped_fragment_=iso%3Astd%3Aiso%3A20715%3Aed-1%3Av1%3Aen)
- [Fermentation: The Key Step in Processing of Black Tea](https://agris.fao.org/search/fr/records/6473b0a3542a3f9f03b31231)
- [Impact of Six Typical Processing Methods on the Chemical Composition of Tea Leaves](https://agris.fao.org/search/en/records/65dff5d763b8185d9cb04493)

### B · 查询改写

**结论：不是同一种茶。** 英文里的 “black tea” 通常对应中文的“红茶”（hongcha），而中文的“黑茶”（heicha）在英文里一般译作 “dark tea”。两者是不同产品类别。

**主要区别（依据工具证据）**

- **命名与翻译**：中文茶类中，hongcha 在英文里常被称为 black tea，尽管冲泡后的茶汤常偏红。这是翻译惯例，并不表示 hongcha 与 heicha（英文常译 dark tea）是同一种产品。若用户只说 “black tea”，英文命名在不同市场可能有歧义，需追问加工传统或产地。
  来源：《Typology of Processed Tea》（年份未标注）

- **加工工艺不同**：
  - 红茶（black tea）制造中，行业所说的 “fermentation（发酵）” 通常指叶片破损并接触空气后的**酶促氧化**，与微生物发酵不同。
    来源：《Fermentation: The Key Step in Processing of Black Tea》（年份未标注）
  - 黑茶（dark tea）在 ISO 20715 中的加工包括杀青、揉捻、**渥堆发酵（piling fermentation）**和干燥；渥堆阶段把它与红茶制造中常被称为发酵的酶促氧化区分开。黑茶产品与地方做法多样，不应把所有黑茶视为同一配方。
    来源：《ISO 20715:2023 Tea — Classification of tea types》

- **相关背景**：茶树品种（cultivar）与茶类（tea type）是不同概念；同一品种用六种典型加工方法可产生不同的化学成分特征，因此品种本身不决定成品茶类或香气，加工同样重要。
  来源：《Impact of Six Typical Processing Methods on the Chemical Composition of Tea Leaves》（年份未标注）

**需要说明的限制**：以上证据未提供各具体黑茶或红茶产品的风味、用途等属性，这类信息我无法验证。本次也没有可用的实时商品价格或库存数据，因此不提供价格与库存。

**人工复核：** 完成；同样正确区分名称；额外召回69后能给出有直接依据的黑茶完整加工步骤。

耗时 19.14s；模型调用 3；Token 输入 5970 / 输出 1070。

最终支持点指标：`{"selected_ids": [76, 65, 81, 69, 78], "support_groups_hit": 1, "support_groups_total": 1, "support_group_coverage": 1.0, "all_available_support": true, "labelled_relevant_precision": 0.6}`。

查询与补检实际记录：

```json
[
  {
    "original_query": "Explain hongcha versus heicha: is black tea the same as dark tea?",
    "rewrite_status": [
      "translated"
    ],
    "rewrite_error_types": [],
    "rejected_variants": 0,
    "queries": [
      {
        "round": 0,
        "query": "Explain hongcha versus heicha: is black tea the same as dark tea?",
        "limit": 15,
        "hits": 15,
        "status": "success"
      },
      {
        "round": 0,
        "query": "解释红茶与黑茶的区别:black tea(红茶)和dark tea(黑茶)是同一种茶吗?",
        "limit": 5,
        "hits": 5,
        "status": "success"
      },
      {
        "round": 0,
        "query": "Explain hongcha versus heicha: is black tea the same as dark tea? | 红茶 黑茶",
        "limit": 5,
        "hits": 5,
        "status": "success"
      },
      {
        "round": 0,
        "query": "红茶和黑茶有什么区别:black tea 与 dark tea 是不是同一种茶?",
        "limit": 5,
        "hits": 5,
        "status": "success"
      }
    ],
    "rerank_status": [
      "success"
    ],
    "retry": false,
    "retry_adopted": false,
    "retry_reasons": [],
    "selected_ids": [
      "76",
      "65",
      "81",
      "69",
      "78"
    ],
    "remaining_issues": [],
    "missing_subjects": []
  }
]
```

实际来源：

- [Typology of Processed Tea](https://agris.fao.org/search/zh/records/68cbbca2f61e5b80b5e93a95)
- [ISO 20715:2023 Tea — Classification of tea types](https://www.iso.org/obp/ui?_escaped_fragment_=iso%3Astd%3Aiso%3A20715%3Aed-1%3Av1%3Aen)
- [Fermentation: The Key Step in Processing of Black Tea](https://agris.fao.org/search/fr/records/6473b0a3542a3f9f03b31231)
- [Impact of Six Typical Processing Methods on the Chemical Composition of Tea Leaves](https://agris.fao.org/search/en/records/65dff5d763b8185d9cb04493)

## 11 · 制造术语缩写与同义表达

**用户：** 请介绍茶叶的CTC工艺，说明它与传统Orthodox工艺的区别。

预先固定目标：解释CTC是crush tear curl，Orthodox和CTC是制造方式，不是基本茶类；不编造未配置的完整生产步骤。

### A · 单查询

**CTC 工艺简介**

CTC 是 “crush, tear, curl”（压碎、撕裂、卷曲）的缩写，指一种制茶方法，成品多为细小、均匀的颗粒。这种工艺常用于制作滋味浓强的茶汤，也常用于茶包。（来源：Tea Board India — Modalities and Scheme Guidelines）

**与传统 Orthodox 工艺的区别**

- Orthodox（传统工艺）指按公认的传统加工规范制造的茶，Tea Board India 认可其适用于红茶和绿茶；CTC 则是一种以“压碎、撕裂、卷曲”为特征、产出细小均匀颗粒的方法。（来源：Tea Board India — Modalities and Scheme Guidelines）
- 两者属于**制造方式（manufacturing approaches）**，与“六大茶类”不是同一分类维度；也就是说，Orthodox 与 CTC 描述的是加工风格，而非茶的种类本身。（来源：Tea Board India — Modalities and Scheme Guidelines）
- 由于 CTC 颗粒较细，通常比大叶整叶茶出味更快，冲泡时应参考生产者说明并依口味调整，不宜套用统一公式。（来源：ISO 20715:2023 Tea — Classification of tea types）

**补充说明**

- 产地名称（如 Darjeeling、Assam、Nilgiri）与加工方式（Orthodox）不可互换：以 Orthodox 风格制作的茶，并不自动等同于大吉岭、阿萨姆或尼尔吉里茶。（来源：Tea Board India — Modalities and Scheme Guidelines）
- 产品描述可同时包含基础加工类型、品种、产地、制造风格、等级、添加成分和产品形态等属性，这些属性回答的是不同问题，不应合并为单一茶类标签。（来源：Typology of Processed Tea）

**无法验证的部分**：本次工具结果未提供 CTC 与 Orthodox 在具体风味、香气或用途上的对比数据，因此这些属性无法验证，不作推断。

**人工复核：** 完成；解释CTC缩写、颗粒形态、与Orthodox不同的制造方式，以及其非基本茶类的分类维度，79支持核心结论。

耗时 20.525s；模型调用 2；Token 输入 4698 / 输出 857。

最终支持点指标：`{"selected_ids": [79, 80, 74, 77, 65], "support_groups_hit": 1, "support_groups_total": 1, "support_group_coverage": 1.0, "all_available_support": true, "labelled_relevant_precision": 0.2}`。

查询与补检实际记录：

```json
[]
```

实际来源：

- [Tea Board India — Modalities and Scheme Guidelines](https://www.teaboard.gov.in/pdf/schemes/Modalities_and_scheme_guidelines_12th_Plan.pdf)
- [ISO 20715:2023 Tea — Classification of tea types](https://www.iso.org/obp/ui?_escaped_fragment_=iso%3Astd%3Aiso%3A20715%3Aed-1%3Av1%3Aen)
- [Typology of Processed Tea](https://agris.fao.org/search/zh/records/68cbbca2f61e5b80b5e93a95)

### B · 查询改写

根据 Tea Board India 的资料，可以这样理解 CTC 工艺及其与 Orthodox 工艺的区别：

**CTC 工艺**
- CTC 是 “crush, tear, curl”（压碎、撕裂、卷曲）的缩写，指一种制茶方法。
- 它产出细小、均匀的颗粒。
- 常用于制作滋味浓强的茶汤，也常用于茶包。

**Orthodox 工艺**
- Orthodox 指按照公认的传统制茶规范进行加工的制造方式。
- Tea Board India 认可 Orthodox 工艺可用于红茶和绿茶的生产。

**两者的主要区别**
- 二者是**制造方式（工艺路线）**的区分，而不是与“六大茶类”同一分类维度上的概念。
- CTC 强调将茶叶处理成细小均匀颗粒；Orthodox 则遵循传统加工规范。
- 需要注意：产品标签和地区标准可能存在用法差异，具体应以所购产品的标注为准。

**补充说明**
- Orthodox 是一种制造风格，不等同于产地名称。Darjeeling、Assam、Nilgiri 属于产地相关名称，采用 Orthodox 工艺的茶并不自动就是这些产地茶。

以上信息来自 Tea Board India — Modalities and Scheme Guidelines（资料年份未标注）。关于 CTC 与 Orthodox 在具体风味、香气上的差异，本次未检索到可验证的证据，无法进一步说明。

**人工复核：** 完成；同样完成CTC/Orthodox区别，没有编造未经配置的完整生产步骤；具体风味差异明确证据不足。

耗时 17.957s；模型调用 3；Token 输入 5778 / 输出 756。

最终支持点指标：`{"selected_ids": [79, 80, 65, 70, 81], "support_groups_hit": 1, "support_groups_total": 1, "support_group_coverage": 1.0, "all_available_support": true, "labelled_relevant_precision": 0.2}`。

查询与补检实际记录：

```json
[
  {
    "original_query": "请介绍茶叶的CTC工艺,说明它与传统Orthodox工艺的区别。",
    "rewrite_status": [
      "translated"
    ],
    "rewrite_error_types": [],
    "rejected_variants": 0,
    "queries": [
      {
        "round": 0,
        "query": "请介绍茶叶的CTC工艺,说明它与传统Orthodox工艺的区别。",
        "limit": 15,
        "hits": 15,
        "status": "success"
      },
      {
        "round": 0,
        "query": "Please introduce the CTC process for tea and explain how it differs from the traditional Orthodox process.",
        "limit": 5,
        "hits": 5,
        "status": "success"
      },
      {
        "round": 0,
        "query": "请介绍茶叶的CTC工艺,说明它与传统Orthodox工艺的区别。 | 加工 processing",
        "limit": 5,
        "hits": 5,
        "status": "success"
      },
      {
        "round": 0,
        "query": "茶叶CTC工艺是什么?它与传统Orthodox工艺有何区别?",
        "limit": 5,
        "hits": 5,
        "status": "success"
      }
    ],
    "rerank_status": [
      "success"
    ],
    "retry": false,
    "retry_adopted": false,
    "retry_reasons": [],
    "selected_ids": [
      "79",
      "80",
      "65",
      "70",
      "81"
    ],
    "remaining_issues": [],
    "missing_subjects": []
  }
]
```

实际来源：

- [Tea Board India — Modalities and Scheme Guidelines](https://www.teaboard.gov.in/pdf/schemes/Modalities_and_scheme_guidelines_12th_Plan.pdf)
- [ISO 20715:2023 Tea — Classification of tea types](https://www.iso.org/obp/ui?_escaped_fragment_=iso%3Astd%3Aiso%3A20715%3Aed-1%3Av1%3Aen)
- [Fermentation: The Key Step in Processing of Black Tea](https://agris.fao.org/search/fr/records/6473b0a3542a3f9f03b31231)

## 12 · 国家缩写与习俗同义表达

**用户：** 请介绍KSA的待客饮茶习俗。

预先固定目标：理解KSA为沙特，有依据介绍待客饮茶而不是仅报告进口量。

### A · 单查询

关于KSA（沙特阿拉伯）的待客饮茶习俗，根据本次检索到的资料，可以介绍以下内容：

**待客顺序**
据 Saudipedia 记载，沙特待客礼仪中通常是先上咖啡、后上茶；如果场合包含午餐或晚餐，茶有时会在餐后较晚时段才端上。这是有记录的习俗，但并非每个家庭都遵循的统一规则。

**风味添加**
茶中可能加入薄荷、婆婆纳（speedwell）或其他芳香叶片。

**一种特色做法**
Saudipedia 还描述了“余烬茶”（ember tea）：在水壶中把水和糖放在余烬上煮沸，然后加入粗茶叶。这种风格与户外露营相关联。

**来源**
- Drinks in Saudi Arabia, Saudipedia（资料年份未标注）

**需要说明的边界**
- 以上是文献记录的习俗，不代表所有沙特家庭的普遍做法。
- 本次检索到的其他资料分别涉及土耳其、阿塞拜疆和约旦的饮茶文化，与KSA无关，未纳入上述介绍。
- 关于KSA待客饮茶的具体茶叶品种、器具规格、冲泡比例等更细的属性，本次证据未覆盖，无法验证，不作补充。

**人工复核：** 完成；正确将KSA理解为沙特，使用59介绍咖啡后上茶、芳香叶片与炭火茶，保留社区差异。

耗时 18.079s；模型调用 2；Token 输入 6275 / 输出 555。

最终支持点指标：`{"selected_ids": [59, 57, 58, 61, 60], "support_groups_hit": 1, "support_groups_total": 1, "support_group_coverage": 1.0, "all_available_support": true, "labelled_relevant_precision": 0.2}`。

查询与补检实际记录：

```json
[]
```

实际来源：

- [Drinks in Saudi Arabia, Saudipedia](https://saudipedia.com/en/drinks-in-saudi-arabia)
- [Culture of Çay (tea), UNESCO Intangible Cultural Heritage](https://ich.unesco.org/en/RL/culture-of-cay-tea-a-symbol-of-identity-hospitality-and-social-interaction-01685?RL=01685)
- [Tea as a Symbol of Common Life and Culture in Anatolia, Go Türkiye](https://goturkiye.com/gastronomy/blog/tea-as-a-symbol-of-common-life-and-culture-in-anatolia)
- [Tea's place in Jordanian popular memory and culture, Petra News Agency](https://petra.gov.jo/index.php/ar/news/%D8%A7%D9%84%D9%8A%D9%88%D9%85-%D8%A7%D9%84%D8%B9%D8%A7%D9%84%D9%85%D9%8A-%D9%84%D9%84%D8%B4%D8%A7%D9%8A-%D9%85%D8%B4%D8%B1%D9%88%D8%A8-%D9%8A%D8%AE%D8%AA%D8%B2%D9%84-%D8%A7%D9%84%D8%B0%D8%A7%D9%83%D8%B1%D8%A9-%D8%A7%D9%84%D8%B4%D8%B9%D8%A8%D9%8A%D8%A9-%D9%88%D9%8A%D8%AD%D8%A7%D9%81%D8%B8-%D8%B9%D9%84%D9%89-%D8%AD%D8%B6%D9%88%D8%B1%D9%87-%D9%81%D9%8A-%D8%A7%D9%84%D8%AB%D9%82%D8%A7%D9%81%D8%A9-%D8%A7%D9%84%D8%A3%D8%B1%D8%AF%D9%86%D9%8A%D8%A9)

### B · 查询改写

关于KSA（沙特阿拉伯）的待客饮茶习俗，根据本次检索到的资料，可以介绍以下内容：

**待客顺序与场合**
据 Saudipedia 记载，沙特待客礼仪中通常先上咖啡、后上茶；如果场合包含午餐或晚餐，茶有时会在餐后较晚时段才端上。这些是文献记录的习俗，并非每个家庭都必须遵循的统一规则。（来源：Drinks in Saudi Arabia, Saudipedia，年份未标注）

**风味添加**
茶中可能加入薄荷、婆婆纳（speedwell）或其他芳香叶片。（来源同上）

**一种特色做法：炭火茶（ember tea）**
Saudipedia 描述的做法是：先在壶中用炭火煮沸水和糖，再加入粗茶叶。这种风格与户外露营场景相关。（来源同上）

**需要说明的边界**
- 上述内容仅为文献记录的习俗，不代表所有家庭或地区的普遍做法。
- 关于KSA茶叶的具体风味、用途等商品属性，本次未检索到可验证的证据，无法提供。
- 本次检索到的其他资料（UNESCO 关于土耳其/阿塞拜疆 çay 文化、Go Türkiye 关于土耳其红茶）均不属于KSA，故不在此作为KSA习俗引用。
- 本次检索到的 FAO 2014 年沙特红茶消费量数据属于历史预测，不是当前实时消费数据，故不在此作为现状引用。

如需了解具体茶叶商品的价格或库存，请提供商品信息，我可另行查询实时数据。

**人工复核：** 完成；同样正确解析KSA并使用59，未把其他国家文化当成沙特；回复较多额外边界说明。

耗时 17.205s；模型调用 3；Token 输入 5800 / 输出 793。

最终支持点指标：`{"selected_ids": [59, 57, 61, 58, 51], "support_groups_hit": 1, "support_groups_total": 1, "support_group_coverage": 1.0, "all_available_support": true, "labelled_relevant_precision": 0.2}`。

查询与补检实际记录：

```json
[
  {
    "original_query": "请介绍KSA的待客饮茶习俗。",
    "rewrite_status": [
      "translated"
    ],
    "rewrite_error_types": [],
    "rejected_variants": 0,
    "queries": [
      {
        "round": 0,
        "query": "请介绍KSA的待客饮茶习俗。",
        "limit": 15,
        "hits": 15,
        "status": "success"
      },
      {
        "round": 0,
        "query": "Please introduce the tea-drinking customs for hosting guests in Saudi Arabia (KSA).",
        "limit": 5,
        "hits": 5,
        "status": "success"
      },
      {
        "round": 0,
        "query": "请介绍沙特阿拉伯(KSA)的待客饮茶习俗。",
        "limit": 5,
        "hits": 5,
        "status": "success"
      },
      {
        "round": 0,
        "query": "请介绍KSA的待客饮茶习俗。 | 沙特阿拉伯 Saudi Arabia 饮茶习惯 tea drinking customs",
        "limit": 5,
        "hits": 5,
        "status": "success"
      }
    ],
    "rerank_status": [
      "success"
    ],
    "retry": false,
    "retry_adopted": false,
    "retry_reasons": [],
    "selected_ids": [
      "59",
      "57",
      "61",
      "58",
      "51"
    ],
    "remaining_issues": [],
    "missing_subjects": []
  }
]
```

实际来源：

- [Drinks in Saudi Arabia, Saudipedia](https://saudipedia.com/en/drinks-in-saudi-arabia)
- [Culture of Çay (tea), UNESCO Intangible Cultural Heritage](https://ich.unesco.org/en/RL/culture-of-cay-tea-a-symbol-of-identity-hospitality-and-social-interaction-01685?RL=01685)
- [Tea as a Symbol of Common Life and Culture in Anatolia, Go Türkiye](https://goturkiye.com/gastronomy/blog/tea-as-a-symbol-of-common-life-and-culture-in-anatolia)
- [Medium-term outlook for tea, 2014 FAO projection](https://www.fao.org/fileadmin/templates/est/meetings/IGGtea21/14-Inf3-CurrentSituation.pdf)

## 13 · 库中不存在的具体配方

**用户：** 请介绍阿联酋皇室专用“月光蓝钻茶”的官方配方。

预先固定目标：明确无此具体产品或官方配方证据，不能从一般茶知识编造配料、比例或皇室背书。

### A · 单查询

关于“阿联酋皇室专用‘月光蓝钻茶’的官方配方”，我无法提供——本次检索到的资料中没有该产品的任何信息，也没有任何证据能证明存在这样一款茶或所谓“官方配方”。

现有资料只涉及以下内容，均与该产品无关：

- **抹茶**：ISO 20715:2023 说明抹茶由遮光栽培的嫩叶经蒸汽杀青、不揉捻干燥、精细研磨制成，是细磨茶产品，并非任意绿茶粉（来源：ISO 20715:2023 Tea — Classification of tea types）。
- **黄茶**：ISO 20715:2023 描述其工艺包括杀青、揉捻或做形、闷黄、干燥，闷黄是其区别性步骤（来源同上）。
- **阿联酋茶叶进口**：2023 年 HS 0902 项下进口额 2.2101 亿美元、73,427.2 吨；这是进口总量，且阿联酋是贸易与转口枢纽，不能等同于本地消费量（来源：Tea imports by country, 2023 (HS 0902)，2023 年）。
- **约旦茶饮文化**：Petra 通讯社报道茶是日常社交生活的一部分，常与薄荷、茴香、鼠尾草等芳香植物同煮，属常见例子而非统一配方（来源：Tea's place in Jordanian popular memory and culture, Petra News Agency）。

如果您指的是某款具体在售商品，请提供准确的商品名称或链接，我可以帮您查询本店的实时价格与库存；若您想了解抹茶、黄茶等真实茶类的工艺或风味，也可以告诉我。

**人工复核：** 正确拒答；说明未找到产品或官方配方证据，未编造原料、比例或皇室背书；但罗列了较多无关茶类/贸易资料。

耗时 21.348s；模型调用 2；Token 输入 6512 / 输出 766。

最终支持点指标：`{"selected_ids": [70, 68, 37, 35, 60], "support_groups_hit": 0, "support_groups_total": 0, "support_group_coverage": null, "all_available_support": null, "labelled_relevant_precision": null}`。

查询与补检实际记录：

```json
[]
```

实际来源：

- [ISO 20715:2023 Tea — Classification of tea types](https://www.iso.org/obp/ui?_escaped_fragment_=iso%3Astd%3Aiso%3A20715%3Aed-1%3Av1%3Aen)
- [Tea imports by country, 2023 (HS 0902)](https://wits.worldbank.org/trade/comtrade/en/country/All/year/2023/tradeflow/Imports/partner/WLD/product/0902)
- [Tea's place in Jordanian popular memory and culture, Petra News Agency](https://petra.gov.jo/index.php/ar/news/%D8%A7%D9%84%D9%8A%D9%88%D9%85-%D8%A7%D9%84%D8%B9%D8%A7%D9%84%D9%85%D9%8A-%D9%84%D9%84%D8%B4%D8%A7%D9%8A-%D9%85%D8%B4%D8%B1%D9%88%D8%A8-%D9%8A%D8%AE%D8%AA%D8%B2%D9%84-%D8%A7%D9%84%D8%B0%D8%A7%D9%83%D8%B1%D8%A9-%D8%A7%D9%84%D8%B4%D8%B9%D8%A8%D9%8A%D8%A9-%D9%88%D9%8A%D8%AD%D8%A7%D9%81%D8%B8-%D8%B9%D9%84%D9%89-%D8%AD%D8%B6%D9%88%D8%B1%D9%87-%D9%81%D9%8A-%D8%A7%D9%84%D8%AB%D9%82%D8%A7%D9%81%D8%A9-%D8%A7%D9%84%D8%A3%D8%B1%D8%AF%D9%86%D9%8A%D8%A9)

### B · 查询改写

关于“阿联酋皇室专用‘月光蓝钻茶’的官方配方”，目前没有可验证的信息。

本次检索到的资料中，没有任何一条提到“月光蓝钻茶”这一名称，也没有阿联酋皇室专用茶的配方记录。现有证据仅涉及以下内容，均与该问题无关：

- 阿联酋茶叶进口与消费预测：FAO 2014年中期展望曾估计阿联酋2013年红茶消费量为4万吨，并预测2023年为63,394吨；该2023年数值是旧预测，并非已核实的实际数据（来源：Medium-term outlook for tea, 2014 FAO projection）。另有世界银行WITS/UN Comtrade数据：2023年阿联酋HS 0902项下茶叶进口额2.2101亿美元、重量73,427.2吨，属毛进口量，因阿联酋是贸易和转口枢纽，进口量不能等同于本地消费量（来源：Tea imports by country, 2023 (HS 0902)）。
- 茶叶分类与加工：ISO 20715:2023 对黄茶、抹茶等茶类的工艺描述（来源：ISO 20715:2023 Tea — Classification of tea types）。
- 沙特待客茶俗：Saudipedia 记载咖啡后上茶、可加薄荷等香叶，以及“ember tea”的做法（来源：Drinks in Saudi Arabia, Saudipedia）。这是沙特的情况，与阿联酋皇室无关。

因此，无法提供该茶的官方配方、原料组成或风味用途等信息——这些属性目前无法验证。如果您指的是某款具体在售商品，请提供准确的商品名称或链接，我可以帮您查询本店的实时价格与库存。

**人工复核：** 正确拒答；同样明确没有名称和皇室配方证据，未编造配方；无关背景仍冗长。

耗时 21.406s；模型调用 3；Token 输入 5737 / 输出 997。

最终支持点指标：`{"selected_ids": [53, 68, 70, 59, 35], "support_groups_hit": 0, "support_groups_total": 0, "support_group_coverage": null, "all_available_support": null, "labelled_relevant_precision": null}`。

查询与补检实际记录：

```json
[
  {
    "original_query": "请介绍阿联酋皇室专用“月光蓝钻茶”的官方配方。",
    "rewrite_status": [
      "translated"
    ],
    "rewrite_error_types": [],
    "rejected_variants": 0,
    "queries": [
      {
        "round": 0,
        "query": "请介绍阿联酋皇室专用“月光蓝钻茶”的官方配方。",
        "limit": 15,
        "hits": 15,
        "status": "success"
      },
      {
        "round": 0,
        "query": "Please introduce the official recipe of the \"Moonlight Blue Diamond Tea\" exclusively used by the royal family of the United Arab Emirates.",
        "limit": 5,
        "hits": 5,
        "status": "success"
      },
      {
        "round": 0,
        "query": "请介绍阿联酋皇室专用“月光蓝钻茶”的官方配方。 | United Arab Emirates",
        "limit": 5,
        "hits": 5,
        "status": "success"
      },
      {
        "round": 0,
        "query": "请介绍阿联酋皇室专用的“月光蓝钻茶”的官方配方是什么?",
        "limit": 5,
        "hits": 5,
        "status": "success"
      }
    ],
    "rerank_status": [
      "success"
    ],
    "retry": false,
    "retry_adopted": false,
    "retry_reasons": [],
    "selected_ids": [
      "53",
      "68",
      "70",
      "59",
      "35"
    ],
    "remaining_issues": [],
    "missing_subjects": []
  }
]
```

实际来源：

- [Medium-term outlook for tea, 2014 FAO projection](https://www.fao.org/fileadmin/templates/est/meetings/IGGtea21/14-Inf3-CurrentSituation.pdf)
- [ISO 20715:2023 Tea — Classification of tea types](https://www.iso.org/obp/ui?_escaped_fragment_=iso%3Astd%3Aiso%3A20715%3Aed-1%3Av1%3Aen)
- [Drinks in Saudi Arabia, Saudipedia](https://saudipedia.com/en/drinks-in-saudi-arabia)
- [Tea imports by country, 2023 (HS 0902)](https://wits.worldbank.org/trade/comtrade/en/country/All/year/2023/tradeflow/Imports/partner/WLD/product/0902)

## 14 · 带数字的冲泡误解

**用户：** 绿茶冲泡水温是否必须固定为80摄氏度？

预先固定目标：说明茶类不规定统一冲泡温度，依产品、叶片、水质、用量和口味调整；不能断言所有绿茶必须80度。

### A · 单查询

不是必须固定为80摄氏度。

依据 ISO 20715:2023《Tea — Classification of tea types》中的冲泡说明：茶类只是冲泡的起点，并不规定统一的时间或温度；叶片等级、颗粒大小、品种、水质、投茶量和期望浓度都会影响萃取，建议按生产商说明并依口味调整，而不是假设同一套冲泡公式适用于所有茶。

因此，绿茶冲泡水温没有“必须固定为80℃”的硬性规定。具体水温、时间等参数，本次工具证据未给出统一数值，无法进一步验证；如你手上有具体茶品，建议以该产品包装或商家说明为准。

**人工复核：** 完成；最终上下文包含74，正确说明茶类不规定统一冲泡温度；本次证据没有rerank_score，表明使用向量降级，不能将该成功归因于正常重排。

耗时 36.017s；模型调用 3；Token 输入 4907 / 输出 382。

最终支持点指标：`{"selected_ids": [65, 74, 81, 58, 61], "support_groups_hit": 1, "support_groups_total": 1, "support_group_coverage": 1.0, "all_available_support": true, "labelled_relevant_precision": 0.2}`。

查询与补检实际记录：

```json
[]
```

实际来源：

- [ISO 20715:2023 Tea — Classification of tea types](https://www.iso.org/obp/ui?_escaped_fragment_=iso%3Astd%3Aiso%3A20715%3Aed-1%3Av1%3Aen)
- [Fermentation: The Key Step in Processing of Black Tea](https://agris.fao.org/search/fr/records/6473b0a3542a3f9f03b31231)
- [Culture of Çay (tea), UNESCO Intangible Cultural Heritage](https://ich.unesco.org/en/RL/culture-of-cay-tea-a-symbol-of-identity-hospitality-and-social-interaction-01685?RL=01685)
- [Tea as a Symbol of Common Life and Culture in Anatolia, Go Türkiye](https://goturkiye.com/gastronomy/blog/tea-as-a-symbol-of-common-life-and-culture-in-anatolia)

### B · 查询改写

关于“绿茶冲泡水温是否必须固定为80摄氏度”，本次检索没有找到能直接回答这个问题的证据，因此无法给出确定结论，也不能据此推断。

现有资料只涉及绿茶加工方式，未涉及冲泡水温：

- 绿茶是鲜叶快速加热使酶失活，再经揉捻、做形或粉碎、干燥等步骤制成；与红茶的关键区别在于绿茶不经过红茶工艺中的有意通气/氧化。具体加热方式和外形因地区和产品而异。（来源：ISO 20715:2023 Tea — Classification of tea types，年份：2023）

因此，“必须固定为80摄氏度”这一说法，我无法用现有证据验证。若您需要，我可以帮您查找是否有其他关于绿茶冲泡参数的资料。

**人工复核：** 失败；六路都召回74，却未将其选入上下文；最终拒绝回答库中可以支持的问题。虽然没有编造数值，核心问答目标未完成。

耗时 28.629s；模型调用 5；Token 输入 7242 / 输出 676。

最终支持点指标：`{"selected_ids": [65, 68, 61, 57, 81], "support_groups_hit": 0, "support_groups_total": 1, "support_group_coverage": 0.0, "all_available_support": false, "labelled_relevant_precision": 0.0}`。

查询与补检实际记录：

```json
[
  {
    "original_query": "绿茶冲泡水温是否必须固定为80摄氏度?",
    "rewrite_status": [
      "translated",
      "translated"
    ],
    "rewrite_error_types": [],
    "rejected_variants": 0,
    "queries": [
      {
        "round": 0,
        "query": "绿茶冲泡水温是否必须固定为80摄氏度?",
        "limit": 15,
        "hits": 15,
        "status": "success"
      },
      {
        "round": 0,
        "query": "Must the brewing water temperature for green tea be fixed at 80 degrees Celsius?",
        "limit": 5,
        "hits": 5,
        "status": "success"
      },
      {
        "round": 0,
        "query": "绿茶冲泡水温是否必须固定为80摄氏度? | green tea brewing",
        "limit": 5,
        "hits": 5,
        "status": "success"
      },
      {
        "round": 0,
        "query": "冲泡绿茶的水温是否一定要固定在80摄氏度?",
        "limit": 5,
        "hits": 5,
        "status": "success"
      },
      {
        "round": 1,
        "query": "绿茶冲泡水温是否必须固定为80摄氏度? | 绿茶 green tea 冲泡 brewing",
        "limit": 7,
        "hits": 7,
        "status": "success"
      },
      {
        "round": 1,
        "query": "绿茶冲泡时水温是否必须始终为80摄氏度?",
        "limit": 8,
        "hits": 8,
        "status": "success"
      }
    ],
    "rerank_status": [
      "success",
      "success"
    ],
    "retry": true,
    "retry_adopted": true,
    "retry_reasons": [
      "subject_topic_gap"
    ],
    "selected_ids": [
      "65",
      "68",
      "61",
      "57",
      "81"
    ],
    "remaining_issues": [
      "subject_topic_gap"
    ],
    "missing_subjects": [
      "green_tea"
    ]
  }
]
```

实际来源：

- [ISO 20715:2023 Tea — Classification of tea types](https://www.iso.org/obp/ui?_escaped_fragment_=iso%3Astd%3Aiso%3A20715%3Aed-1%3Av1%3Aen)
- [Tea as a Symbol of Common Life and Culture in Anatolia, Go Türkiye](https://goturkiye.com/gastronomy/blog/tea-as-a-symbol-of-common-life-and-culture-in-anatolia)
- [Culture of Çay (tea), UNESCO Intangible Cultural Heritage](https://ich.unesco.org/en/RL/culture-of-cay-tea-a-symbol-of-identity-hospitality-and-social-interaction-01685?RL=01685)
- [Fermentation: The Key Step in Processing of Black Tea](https://agris.fao.org/search/fr/records/6473b0a3542a3f9f03b31231)

## 15 · 三茶类证据覆盖

**用户：** 说明绿茶、红茶和白茶的加工区别。

预先固定目标：同时介绍绿茶加热、红茶氧化、白茶萎凋/干燥，不能漏掉一类或用泛泛分类清单代替工艺。

### A · 单查询

根据本次检索到的资料，绿茶、红茶和白茶在加工上的主要区别如下：

**绿茶**
- 关键步骤是“快速加热鲜叶以钝化酶”，之后可能包括揉捻、做形或粉碎、干燥等步骤。
- 与红茶相比，绿茶的决定性加工差异在于：不经过红茶那种刻意通气/氧化（发酵）的过程。
- 具体加热方式和外形因地区和产品而异。
- 来源：ISO 20715:2023 Tea — Classification of tea types（年份未标注）

**红茶**
- 红茶加工中的“发酵（fermentation）”是行业用语，指叶片破损并暴露于空气后发生的酶促氧化，与微生物发酵不同。
- 绿茶几乎不进行刻意氧化，乌龙茶为部分氧化，黑茶可能另有渥堆或后发酵阶段。
- 来源：Fermentation: The Key Step in Processing of Black Tea（年份未标注）

**白茶**
- ISO 20715 将白茶描述为：采摘的茶芽经一次萎凋和干燥阶段制成。
- “白茶”指的是山茶属茶树的茶类型及一种加工方式，而不是白色花朵或草本植物泡制的饮品。
- 来源：ISO 20715:2023 Tea — Classification of tea types（年份未标注）

**补充说明**
- 茶树品种与茶类是两个不同概念：红茶、绿茶、乌龙茶、白茶、黄茶、黑茶描述的是加工后的产品类型；同一品种用六种典型加工方法可产生不同的化学成分特征，因此品种本身并不决定成品茶类或香气，加工方式同样重要。
- 来源：Impact of Six Typical Processing Methods on the Chemical Composition of Tea Leaves（年份未标注）

如需进一步了解某一茶类的具体工艺细节，可以告诉我。

**人工复核：** 完成；用65/81/66分别说明绿茶灭酶、红茶氧化、白茶萎凋干燥，没有漏类。

耗时 27.809s；模型调用 2；Token 输入 4605 / 输出 797。

最终支持点指标：`{"selected_ids": [65, 81, 78, 66, 79], "support_groups_hit": 3, "support_groups_total": 3, "support_group_coverage": 1.0, "all_available_support": true, "labelled_relevant_precision": 0.6}`。

查询与补检实际记录：

```json
[]
```

实际来源：

- [ISO 20715:2023 Tea — Classification of tea types](https://www.iso.org/obp/ui?_escaped_fragment_=iso%3Astd%3Aiso%3A20715%3Aed-1%3Av1%3Aen)
- [Fermentation: The Key Step in Processing of Black Tea](https://agris.fao.org/search/fr/records/6473b0a3542a3f9f03b31231)
- [Impact of Six Typical Processing Methods on the Chemical Composition of Tea Leaves](https://agris.fao.org/search/en/records/65dff5d763b8185d9cb04493)
- [Tea Board India — Modalities and Scheme Guidelines](https://www.teaboard.gov.in/pdf/schemes/Modalities_and_scheme_guidelines_12th_Plan.pdf)

### B · 查询改写

**绿茶、红茶、白茶的加工区别**

- **绿茶**：鲜叶先快速加热（杀青）使酶失活，之后可能经过揉捻、做形或粉碎、干燥等步骤。与红茶的关键区别是：绿茶不经过红茶那种有意的氧化（通氧）工序。具体加热方式和外形因产地和产品而异。（来源：ISO 20715:2023 Tea — Classification of tea types）

- **红茶**：制茶中的“发酵”通常指叶片破损并接触空气后的酶促氧化，与微生物发酵不同。红茶的核心工序就是这种酶促氧化。（来源：Fermentation: The Key Step in Processing of Black Tea）

- **白茶**：按 ISO 20715 的描述，是采摘的茶芽经一次萎凋和干燥两个阶段制成。白茶指的是山茶属茶树的茶类及一种加工方式，不是用白色花朵或草本泡的饮品。（来源：ISO 20715:2023 Tea — Classification of tea types）

**补充说明**：茶树品种与茶类是两个概念——同一品种用六种典型加工方法可得到不同的化学成分特征，因此品种本身不决定成品茶类或香气，加工方式同样重要。（来源：Impact of Six Typical Processing Methods on the Chemical Composition of Tea Leaves）

如需进一步了解某一类的具体工艺细节，可以告诉我。

**人工复核：** 完成；同样覆盖三类制造区别，主要事实与最终三个支持片段一致。

耗时 24.643s；模型调用 3；Token 输入 5818 / 输出 744。

最终支持点指标：`{"selected_ids": [65, 66, 81, 78, 79], "support_groups_hit": 3, "support_groups_total": 3, "support_group_coverage": 1.0, "all_available_support": true, "labelled_relevant_precision": 0.6}`。

查询与补检实际记录：

```json
[
  {
    "original_query": "说明绿茶、红茶和白茶的加工区别。",
    "rewrite_status": [
      "translated"
    ],
    "rewrite_error_types": [],
    "rejected_variants": 0,
    "queries": [
      {
        "round": 0,
        "query": "说明绿茶、红茶和白茶的加工区别。",
        "limit": 15,
        "hits": 15,
        "status": "success"
      },
      {
        "round": 0,
        "query": "Explain the processing differences among green tea, black tea, and white tea.",
        "limit": 5,
        "hits": 5,
        "status": "success"
      },
      {
        "round": 0,
        "query": "说明绿茶、红茶和白茶的加工区别。 | green tea black tea white tea processing",
        "limit": 5,
        "hits": 5,
        "status": "success"
      },
      {
        "round": 0,
        "query": "绿茶、红茶与白茶在加工工艺上有何区别?",
        "limit": 5,
        "hits": 5,
        "status": "success"
      }
    ],
    "rerank_status": [
      "success"
    ],
    "retry": false,
    "retry_adopted": false,
    "retry_reasons": [],
    "selected_ids": [
      "65",
      "66",
      "81",
      "78",
      "79"
    ],
    "remaining_issues": [],
    "missing_subjects": []
  }
]
```

实际来源：

- [ISO 20715:2023 Tea — Classification of tea types](https://www.iso.org/obp/ui?_escaped_fragment_=iso%3Astd%3Aiso%3A20715%3Aed-1%3Av1%3Aen)
- [Fermentation: The Key Step in Processing of Black Tea](https://agris.fao.org/search/fr/records/6473b0a3542a3f9f03b31231)
- [Impact of Six Typical Processing Methods on the Chemical Composition of Tea Leaves](https://agris.fao.org/search/en/records/65dff5d763b8185d9cb04493)
- [Tea Board India — Modalities and Scheme Guidelines](https://www.teaboard.gov.in/pdf/schemes/Modalities_and_scheme_guidelines_12th_Plan.pdf)
