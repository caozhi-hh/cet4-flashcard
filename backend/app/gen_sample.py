"""生成示例四级词库（50个高频词）"""
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

words = [
    {"word": "abandon", "phonetic_us": "/əˈbændən/", "phonetic_uk": "/əˈbændən/", "definition": "v. 放弃；抛弃", "pos": "v.", "example": "He abandoned his car in the snow.", "example_cn": "他把车丢弃在雪地里。", "frequency": 1},
    {"word": "absolute", "phonetic_us": "/ˈæbsəluːt/", "phonetic_uk": "/ˈæbsəluːt/", "definition": "adj. 绝对的；完全的", "pos": "adj.", "example": "I have absolute confidence in her.", "example_cn": "我对她有绝对的信心。", "frequency": 2},
    {"word": "absorb", "phonetic_us": "/əbˈzɔːrb/", "phonetic_uk": "/əbˈzɔːb/", "definition": "v. 吸收；吸引注意力", "pos": "v.", "example": "Plants absorb carbon dioxide.", "example_cn": "植物吸收二氧化碳。", "frequency": 3},
    {"word": "abstract", "phonetic_us": "/ˈæbstrækt/", "phonetic_uk": "/ˈæbstrækt/", "definition": "adj. 抽象的；n. 摘要", "pos": "adj.", "example": "The concept is too abstract for children.", "example_cn": "这个概念对孩子们来说太抽象了。", "frequency": 4},
    {"word": "academic", "phonetic_us": "/ˌækəˈdemɪk/", "phonetic_uk": "/ˌækəˈdemɪk/", "definition": "adj. 学术的；学业的", "pos": "adj.", "example": "She has an outstanding academic record.", "example_cn": "她有出色的学业成绩。", "frequency": 5},
    {"word": "accelerate", "phonetic_us": "/əkˈseləreɪt/", "phonetic_uk": "/əkˈseləreɪt/", "definition": "v. 加速；促进", "pos": "v.", "example": "The car accelerated rapidly.", "example_cn": "汽车迅速加速。", "frequency": 6},
    {"word": "accomplish", "phonetic_us": "/əˈkɑːmplɪʃ/", "phonetic_uk": "/əˈkʌmplɪʃ/", "definition": "v. 完成；实现", "pos": "v.", "example": "She accomplished all her goals.", "example_cn": "她完成了所有的目标。", "frequency": 7},
    {"word": "accurate", "phonetic_us": "/ˈækjərət/", "phonetic_uk": "/ˈækjərət/", "definition": "adj. 准确的；精确的", "pos": "adj.", "example": "The information is not accurate.", "example_cn": "这个信息不准确。", "frequency": 8},
    {"word": "achieve", "phonetic_us": "/əˈtʃiːv/", "phonetic_uk": "/əˈtʃiːv/", "definition": "v. 实现；取得", "pos": "v.", "example": "He achieved great success in business.", "example_cn": "他在商业上取得了巨大成功。", "frequency": 9},
    {"word": "acknowledge", "phonetic_us": "/əkˈnɑːlɪdʒ/", "phonetic_uk": "/əkˈnɒlɪdʒ/", "definition": "v. 承认；确认", "pos": "v.", "example": "She acknowledged her mistake.", "example_cn": "她承认了自己的错误。", "frequency": 10},
    {"word": "acquire", "phonetic_us": "/əˈkwaɪər/", "phonetic_uk": "/əˈkwaɪər/", "definition": "v. 获得；习得", "pos": "v.", "example": "She acquired a taste for classical music.", "example_cn": "她培养了对古典音乐的品味。", "frequency": 11},
    {"word": "adapt", "phonetic_us": "/əˈdæpt/", "phonetic_uk": "/əˈdæpt/", "definition": "v. 适应；改编", "pos": "v.", "example": "You must adapt to the new environment.", "example_cn": "你必须适应新环境。", "frequency": 12},
    {"word": "adequate", "phonetic_us": "/ˈædɪkwət/", "phonetic_uk": "/ˈædɪkwət/", "definition": "adj. 充足的；足够的", "pos": "adj.", "example": "The food supply is adequate for the winter.", "example_cn": "食物供应足够过冬。", "frequency": 13},
    {"word": "adjust", "phonetic_us": "/əˈdʒʌst/", "phonetic_uk": "/əˈdʒʌst/", "definition": "v. 调整；适应", "pos": "v.", "example": "You need to adjust the settings.", "example_cn": "你需要调整设置。", "frequency": 14},
    {"word": "admire", "phonetic_us": "/ədˈmaɪər/", "phonetic_uk": "/ədˈmaɪər/", "definition": "v. 钦佩；赞赏", "pos": "v.", "example": "I admire her courage.", "example_cn": "我钦佩她的勇气。", "frequency": 15},
    {"word": "adventure", "phonetic_us": "/ədˈventʃər/", "phonetic_uk": "/ədˈventʃər/", "definition": "n. 冒险；奇遇", "pos": "n.", "example": "Life is an adventure.", "example_cn": "生活就是一场冒险。", "frequency": 16},
    {"word": "advocate", "phonetic_us": "/ˈædvəkeɪt/", "phonetic_uk": "/ˈædvəkət/", "definition": "v. 提倡；n. 提倡者", "pos": "v./n.", "example": "She advocates for human rights.", "example_cn": "她提倡人权。", "frequency": 17},
    {"word": "affect", "phonetic_us": "/əˈfekt/", "phonetic_uk": "/əˈfekt/", "definition": "v. 影响；感动", "pos": "v.", "example": "The weather affects our mood.", "example_cn": "天气影响我们的心情。", "frequency": 18},
    {"word": "afford", "phonetic_us": "/əˈfɔːrd/", "phonetic_uk": "/əˈfɔːd/", "definition": "v. 买得起；承担得起", "pos": "v.", "example": "I cannot afford a new car.", "example_cn": "我买不起新车。", "frequency": 19},
    {"word": "aggressive", "phonetic_us": "/əˈɡresɪv/", "phonetic_uk": "/əˈɡresɪv/", "definition": "adj. 有进取心的；好斗的", "pos": "adj.", "example": "He is an aggressive salesman.", "example_cn": "他是个有进取心的销售员。", "frequency": 20},
    {"word": "allocate", "phonetic_us": "/ˈæləkeɪt/", "phonetic_uk": "/ˈæləkeɪt/", "definition": "v. 分配；拨出", "pos": "v.", "example": "The government allocated funds for education.", "example_cn": "政府拨出了教育经费。", "frequency": 21},
    {"word": "alternative", "phonetic_us": "/ɔːlˈtɜːrnətɪv/", "phonetic_uk": "/ɔːlˈtɜːnətɪv/", "definition": "n. 替代选择；adj. 替代的", "pos": "n./adj.", "example": "We have no alternative but to wait.", "example_cn": "除了等待我们别无选择。", "frequency": 22},
    {"word": "ambition", "phonetic_us": "/æmˈbɪʃn/", "phonetic_uk": "/æmˈbɪʃn/", "definition": "n. 雄心；抱负", "pos": "n.", "example": "His ambition is to become a doctor.", "example_cn": "他的志向是成为一名医生。", "frequency": 23},
    {"word": "analyze", "phonetic_us": "/ˈænəlaɪz/", "phonetic_uk": "/ˈænəlaɪz/", "definition": "v. 分析", "pos": "v.", "example": "We need to analyze the data carefully.", "example_cn": "我们需要仔细分析数据。", "frequency": 24},
    {"word": "annual", "phonetic_us": "/ˈænjuəl/", "phonetic_uk": "/ˈænjuəl/", "definition": "adj. 年度的；每年的", "pos": "adj.", "example": "The annual meeting is in March.", "example_cn": "年会定在三月。", "frequency": 25},
    {"word": "anticipate", "phonetic_us": "/ænˈtɪsɪpeɪt/", "phonetic_uk": "/ænˈtɪsɪpeɪt/", "definition": "v. 预期；期望", "pos": "v.", "example": "We anticipate a busy holiday season.", "example_cn": "我们预计假期会很忙。", "frequency": 26},
    {"word": "apparent", "phonetic_us": "/əˈpærənt/", "phonetic_uk": "/əˈpærənt/", "definition": "adj. 明显的；表面上的", "pos": "adj.", "example": "It was apparent that she was tired.", "example_cn": "很明显她累了。", "frequency": 27},
    {"word": "appeal", "phonetic_us": "/əˈpiːl/", "phonetic_uk": "/əˈpiːl/", "definition": "v. 呼吁；吸引；n. 上诉", "pos": "v./n.", "example": "The idea appeals to me.", "example_cn": "这个想法对我有吸引力。", "frequency": 28},
    {"word": "appreciate", "phonetic_us": "/əˈpriːʃieɪt/", "phonetic_uk": "/əˈpriːʃieɪt/", "definition": "v. 感激；欣赏；增值", "pos": "v.", "example": "I really appreciate your help.", "example_cn": "我真的很感激你的帮助。", "frequency": 29},
    {"word": "approach", "phonetic_us": "/əˈproʊtʃ/", "phonetic_uk": "/əˈprəʊtʃ/", "definition": "v. 接近；n. 方法", "pos": "v./n.", "example": "We need a new approach to this problem.", "example_cn": "我们需要用新方法解决这个问题。", "frequency": 30},
    {"word": "appropriate", "phonetic_us": "/əˈproʊpriət/", "phonetic_uk": "/əˈprəʊpriət/", "definition": "adj. 适当的；合适的", "pos": "adj.", "example": "This is not appropriate behavior.", "example_cn": "这种行为是不恰当的。", "frequency": 31},
    {"word": "approve", "phonetic_us": "/əˈpruːv/", "phonetic_uk": "/əˈpruːv/", "definition": "v. 批准；赞成", "pos": "v.", "example": "The committee approved the plan.", "example_cn": "委员会批准了该计划。", "frequency": 32},
    {"word": "arrange", "phonetic_us": "/əˈreɪndʒ/", "phonetic_uk": "/əˈreɪndʒ/", "definition": "v. 安排；排列", "pos": "v.", "example": "Can you arrange a meeting for tomorrow?", "example_cn": "你能安排明天的会议吗？", "frequency": 33},
    {"word": "assume", "phonetic_us": "/əˈsuːm/", "phonetic_uk": "/əˈsjuːm/", "definition": "v. 假设；承担", "pos": "v.", "example": "I assume you have read the report.", "example_cn": "我假设你已经读过报告了。", "frequency": 34},
    {"word": "assure", "phonetic_us": "/əˈʃʊr/", "phonetic_uk": "/əˈʃʊər/", "definition": "v. 保证；使确信", "pos": "v.", "example": "I assure you everything is fine.", "example_cn": "我向你保证一切都没问题。", "frequency": 35},
    {"word": "atmosphere", "phonetic_us": "/ˈætməsfɪr/", "phonetic_uk": "/ˈætməsfɪər/", "definition": "n. 气氛；大气层", "pos": "n.", "example": "The atmosphere in the room was tense.", "example_cn": "房间里的气氛很紧张。", "frequency": 36},
    {"word": "attach", "phonetic_us": "/əˈtætʃ/", "phonetic_uk": "/əˈtætʃ/", "definition": "v. 附加；连接", "pos": "v.", "example": "Please attach a recent photo to the form.", "example_cn": "请在表格上附上一张近照。", "frequency": 37},
    {"word": "attempt", "phonetic_us": "/əˈtempt/", "phonetic_uk": "/əˈtempt/", "definition": "v./n. 尝试；企图", "pos": "v./n.", "example": "She attempted to break the world record.", "example_cn": "她试图打破世界纪录。", "frequency": 38},
    {"word": "attribute", "phonetic_us": "/əˈtrɪbjuːt/", "phonetic_uk": "/əˈtrɪbjuːt/", "definition": "v. 归因于；n. 属性", "pos": "v./n.", "example": "He attributed his success to hard work.", "example_cn": "他把成功归因于努力工作。", "frequency": 39},
    {"word": "authority", "phonetic_us": "/əˈθɔːrəti/", "phonetic_uk": "/əˈθɒrəti/", "definition": "n. 权威；当局", "pos": "n.", "example": "The authorities investigated the incident.", "example_cn": "当局调查了这起事件。", "frequency": 40},
    {"word": "available", "phonetic_us": "/əˈveɪləbl/", "phonetic_uk": "/əˈveɪləbl/", "definition": "adj. 可用的；有空的", "pos": "adj.", "example": "Is this item available in blue?", "example_cn": "这件商品有蓝色的吗？", "frequency": 41},
    {"word": "balance", "phonetic_us": "/ˈbæləns/", "phonetic_uk": "/ˈbæləns/", "definition": "n. 平衡；余额；v. 使平衡", "pos": "n./v.", "example": "You need to balance work and life.", "example_cn": "你需要平衡工作和生活。", "frequency": 42},
    {"word": "barrier", "phonetic_us": "/ˈbæriər/", "phonetic_uk": "/ˈbæriər/", "definition": "n. 障碍；屏障", "pos": "n.", "example": "Language can be a barrier to communication.", "example_cn": "语言可能成为沟通的障碍。", "frequency": 43},
    {"word": "behalf", "phonetic_us": "/bɪˈhæf/", "phonetic_uk": "/bɪˈhɑːf/", "definition": "n. 代表；利益", "pos": "n.", "example": "I am writing on behalf of my mother.", "example_cn": "我代表我母亲写信。", "frequency": 44},
    {"word": "benefit", "phonetic_us": "/ˈbenɪfɪt/", "phonetic_uk": "/ˈbenɪfɪt/", "definition": "n. 好处；利益；v. 有益于", "pos": "n./v.", "example": "Regular exercise has many health benefits.", "example_cn": "经常锻炼有很多健康益处。", "frequency": 45},
    {"word": "boundary", "phonetic_us": "/ˈbaʊndri/", "phonetic_uk": "/ˈbaʊndri/", "definition": "n. 边界；界限", "pos": "n.", "example": "The river forms the boundary between two countries.", "example_cn": "这条河构成两国的边界。", "frequency": 46},
    {"word": "budget", "phonetic_us": "/ˈbʌdʒɪt/", "phonetic_uk": "/ˈbʌdʒɪt/", "definition": "n. 预算", "pos": "n.", "example": "The project was completed within budget.", "example_cn": "项目在预算内完成了。", "frequency": 47},
    {"word": "capacity", "phonetic_us": "/kəˈpæsəti/", "phonetic_uk": "/kəˈpæsəti/", "definition": "n. 能力；容量", "pos": "n.", "example": "The stadium has a capacity of 50,000.", "example_cn": "体育场能容纳五万人。", "frequency": 48},
    {"word": "certificate", "phonetic_us": "/sərˈtɪfɪkət/", "phonetic_uk": "/səˈtɪfɪkət/", "definition": "n. 证书；证明", "pos": "n.", "example": "She received a certificate of achievement.", "example_cn": "她获得了成就证书。", "frequency": 49},
    {"word": "challenge", "phonetic_us": "/ˈtʃælɪndʒ/", "phonetic_uk": "/ˈtʃælɪndʒ/", "definition": "n./v. 挑战", "pos": "n./v.", "example": "Learning a new language is a challenge.", "example_cn": "学习一门新语言是一个挑战。", "frequency": 50},
]

with open("cet4_words.json", "w", encoding="utf-8") as f:
    json.dump(words, f, ensure_ascii=False, indent=2)
print(f"Generated {len(words)} sample words -> cet4_words.json")
