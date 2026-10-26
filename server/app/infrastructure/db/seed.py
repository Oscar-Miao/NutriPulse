from __future__ import annotations

import re

from app.infrastructure.db.database import transaction
from app.shared.util import as_json, new_id


FOODS = [
    ("oats", "燕麦", 389, 66.3, 16.9, 6.9, 10.6, []),
    ("egg", "鸡蛋", 143, 0.7, 12.6, 9.5, 0, ["egg"]),
    ("chicken", "鸡胸肉", 165, 0, 31, 3.6, 0, []),
    ("rice", "米饭", 116, 25.9, 2.6, 0.3, 0.3, []),
    ("broccoli", "西兰花", 34, 6.6, 2.8, 0.4, 2.6, []),
    ("tofu", "豆腐", 76, 1.9, 8.1, 4.8, 0.3, ["soy"]),
    ("banana", "香蕉", 89, 22.8, 1.1, 0.3, 2.6, []),
    ("salmon", "三文鱼", 208, 0, 20, 13, 0, ["fish"]),
    ("yogurt", "无糖酸奶", 63, 7, 5.3, 1.6, 0, ["milk"]),
    ("sweet_potato", "红薯", 86, 20.1, 1.6, 0.1, 3, []),
    ("beef", "瘦牛肉", 170, 0, 26, 6, 0, []),
    ("peanut", "花生", 567, 16.1, 25.8, 49.2, 8.5, ["peanut"]),
]

# Demo cooking alternatives, matched by energy per serving for preview only.
# Different ingredients may require changed cooking instructions or seasoning.
FOOD_SUBSTITUTIONS = [
    ("chicken", "beef"), ("chicken", "tofu"),
    ("beef", "chicken"), ("tofu", "chicken"),
    ("salmon", "chicken"), ("egg", "tofu"),
    ("rice", "sweet_potato"), ("sweet_potato", "rice"),
    ("oats", "sweet_potato"),
]

RECIPES = [
    ("r1", "鸡胸肉西兰花饭", "self_cook", 20, ["鸡胸肉 150g", "米饭 150g", "西兰花 200g"],
     ["鸡胸肉煎熟", "西兰花焯水", "配米饭装盘"], [("chicken",150),("rice",150),("broccoli",200)], []),
    ("r2", "三文鱼红薯碗", "self_cook", 25, ["三文鱼 120g", "红薯 180g", "西兰花 100g"],
     ["三文鱼煎熟", "红薯蒸熟", "加入西兰花"], [("salmon",120),("sweet_potato",180),("broccoli",100)], ["fish"]),
    ("r3", "燕麦酸奶香蕉杯", "self_cook", 5, ["燕麦 50g", "无糖酸奶 150g", "香蕉 100g"],
     ["燕麦和酸奶混合", "香蕉切片加入"], [("oats",50),("yogurt",150),("banana",100)], ["milk"]),
    ("r4", "牛肉豆腐米饭", "self_cook", 20, ["瘦牛肉 130g", "豆腐 150g", "米饭 160g"],
     ["牛肉炒熟", "豆腐加热", "配米饭食用"], [("beef",130),("tofu",150),("rice",160)], ["soy"]),
    ("r5", "鸡蛋燕麦早餐", "self_cook", 10, ["鸡蛋 100g", "燕麦 60g", "香蕉 100g"],
     ["鸡蛋煮熟", "燕麦加水煮熟", "配香蕉食用"], [("egg",100),("oats",60),("banana",100)], ["egg"]),
    ("r6", "鸡胸肉红薯轻食", "self_cook", 20, ["鸡胸肉 120g", "红薯 150g", "西兰花 150g"],
     ["鸡胸肉煎熟", "红薯蒸熟", "西兰花焯水"], [("chicken",120),("sweet_potato",150),("broccoli",150)], []),
    ("r7", "外卖鸡胸肉米饭轻食", "takeout", 0, [],
     ["选择标注食材与重量的商家", "要求酱汁分装、少油", "实际食用后按包装或称量修正"],
     [("chicken",150),("rice",150),("broccoli",150)], []),
    ("r8", "外卖牛肉红薯碗", "takeout", 0, [],
     ["选择可确认牛肉及配菜成分的商家", "酱汁分装，避免额外加油", "核对实际份量"],
     [("beef",130),("sweet_potato",180),("broccoli",120)], []),
    ("r9", "堂食清蒸鱼配饭", "dine_in", 0, [],
     ["向餐厅确认鱼类与调味料", "选择清蒸做法，米饭单独计量", "拍照或估重后记录实际摄入"],
     [("salmon",120),("rice",150),("broccoli",150)], ["fish"]),
    ("r10", "堂食牛肉蔬菜饭", "dine_in", 0, [],
     ["点餐时确认菜品不含过敏食材", "少油少酱汁", "米饭与主菜分开估量"],
     [("beef",130),("rice",150),("broccoli",150)], []),
    ("r11", "便利店酸奶燕麦香蕉组合", "convenience", 0, [],
     ["选择无糖酸奶并核对标签", "按包装净含量记录", "不额外添加糖浆"],
     [("yogurt",200),("oats",50),("banana",100)], ["milk"]),
    ("r12", "便利店鸡胸肉饭团组合", "convenience", 0, [],
     ["购买独立包装鸡胸肉和米饭", "查看配料表及过敏原", "按包装营养标签修正热量"],
     [("chicken",120),("rice",160),("broccoli",100)], []),
    ("r13", "外卖豆腐西兰花饭", "takeout", 0, [],
     ["选择配料清晰的豆腐轻食", "确认不含额外花生或乳制品酱汁", "米饭与酱汁分开计量"],
     [("tofu",200),("rice",150),("broccoli",180)], ["soy"]),
    ("r14", "堂食鸡胸肉蔬菜饭", "dine_in", 0, [],
     ["确认鸡肉已充分加热", "少油，米饭单独估量", "按实际份量修改预记记录"],
     [("chicken",150),("rice",150),("broccoli",180)], []),
    ("r15", "便利店鸡蛋燕麦香蕉餐", "convenience", 0, [],
     ["购买独立包装鸡蛋与无糖燕麦", "核对过敏原标签", "按净含量记录"],
     [("egg",100),("oats",60),("banana",100)], ["egg"]),
]

# Demo-only approximate ingredient/order costs, not live store prices or a quote.
# Flavor tags describe the seeded preparation, not a verified restaurant recipe.
RECIPE_METADATA = {
    "r1": (18, ["清淡", "咸鲜"]), "r2": (32, ["清淡", "咸鲜"]),
    "r3": (12, ["甜口", "清淡"]), "r4": (25, ["咸鲜"]),
    "r5": (10, ["清淡"]), "r6": (17, ["清淡", "咸鲜"]),
    "r7": (28, ["清淡", "咸鲜"]), "r8": (34, ["咸鲜"]),
    "r9": (48, ["清淡", "咸鲜"]), "r10": (38, ["咸鲜"]),
    "r11": (19, ["甜口", "清淡"]), "r12": (24, ["咸鲜"]),
    "r13": (25, ["清淡", "咸鲜"]), "r14": (36, ["清淡", "咸鲜"]),
    "r15": (17, ["清淡"]),
}

PLANS = [
    ("PLAN-01", "零基础启动：全身适应", "beginner", "maintenance", 4, 3,
     "每周三次全身力量与两次轻快走，建立动作习惯。",
     [(1,"全身 A",["杯式深蹲 3×10","跪姿俯卧撑 3×8","坐姿划船 3×10","臀桥 3×12","平板支撑 3×20 秒"]),
      (3,"全身 B",["罗马尼亚硬拉 3×10","哑铃卧推 3×10","高位下拉 3×10","台阶踏步 2×10/侧","死虫 3×8/侧"]),
      (5,"全身 C",["腿举 3×12","哑铃肩推 3×10","绳索划船 3×12","髋外展 2×15","农夫走 3×30 秒"])]),
    ("PLAN-02", "新手减脂：力量与有氧", "beginner", "fat_loss", 8, 4,
     "每周两次全身力量和两次有氧，优先保持肌肉。",
     [(1,"全身 A",["深蹲 4×8","卧推 4×8","划船 4×10","卷腹 3×12"]),
      (2,"有氧",["Zone 2 慢跑/单车 35-45 分钟"]),
      (4,"全身 B",["硬拉 3×6","肩推 4×8","高位下拉 4×10","弓步 3×10/侧"]),
      (6,"间歇",["热身 10 分钟","1 分钟快 + 2 分钟慢 × 6","冷身 8 分钟"])]),
    ("PLAN-03", "新手增肌：上下肢", "intermediate", "muscle_gain", 8, 4,
     "上下肢各两次，逐步增加有效训练容量。",
     [(1,"上肢 A",["卧推 4×6-8","划船 4×8-10","上斜哑铃推 3×10","高位下拉 3×10","侧平举 3×15","臂屈伸 2×12"]),
      (2,"下肢 A",["深蹲 4×6-8","罗马尼亚硬拉 3×8","腿举 3×12","腿弯举 3×12","提踵 4×12"]),
      (4,"上肢 B",["肩推 4×6-8","引体/下拉 4×8","器械推胸 3×12","单臂划船 3×10","弯举 3×12","面拉 3×15"]),
      (5,"下肢 B",["硬拉 3×5","前蹲 3×8","保加利亚分腿蹲 3×10/侧","髋推 3×10","平板支撑 3×30 秒"])]),
    ("PLAN-04", "中级塑形：推拉腿", "intermediate", "muscle_gain", 8, 6,
     "推、拉、腿循环两次，第二轮调整次数区间。",
     [(1,"推 A",["卧推 4×6-8","肩推 3×8-10","上斜推 3×10","侧平举 3×15","臂屈伸 2×12"]),
      (2,"拉 A",["辅助引体 4×6-8","划船 4×8-10","后束飞鸟 3×15","面拉 3×15","弯举 2×12"]),
      (3,"腿 A",["深蹲 4×6-8","腿举 3×12","腿弯举 3×12","提踵 3×15","卷腹 3×12"]),
      (4,"推 B",["器械推胸 4×8-10","哑铃肩推 3×10","上斜哑铃推 3×10","侧平举 3×15","绳索下压 2×12"]),
      (5,"拉 B",["硬拉 3×5","高位下拉 4×10","单臂划船 3×10","后束飞鸟 3×15","弯举 2×12"]),
      (6,"腿 B",["前蹲 4×8","罗马尼亚硬拉 3×10","弓步 3×10/侧","提踵 3×15","平板支撑 3×30 秒"])]),
    ("PLAN-05", "高阶力量：三大项", "advanced", "muscle_gain", 9, 5,
     "深蹲、卧推、硬拉的积累、强化、减量和测试周期。",
     [(1,"深蹲主项",["深蹲 4×5","暂停深蹲 3×5","腿举 3×10"]),
      (2,"卧推容量",["卧推 5×5","杠铃划船 4×8","上斜哑铃推 3×10"]),
      (3,"硬拉主项",["硬拉 4×4","罗马尼亚硬拉 3×8","高位下拉 3×10"]),
      (5,"卧推强度",["卧推 4×4","肩推 3×6","面拉 3×15"]),
      (6,"深蹲变式",["前蹲 4×5","技术硬拉 3×5","臀桥 3×10"])]),
    ("PLAN-06", "恢复回归：低冲击", "beginner", "recovery", 6, 3,
     "一般体能回归训练，不作为医疗康复处方。",
     [(1,"低冲击 A",["箱式深蹲 2×8","弹力带划船 2×10","墙面俯卧撑 2×8"]),
      (3,"低冲击 B",["轻阻力髋铰链 2×8","低台阶 2×8/侧","呼吸训练 2×6"]),
      (5,"低冲击 C",["活动度练习 2×8","箱式深蹲 2×8","弹力带划船 2×10"])]),
]

PLAN_DETAILS = {
    "PLAN-01": ("久坐或首次系统训练的成年人", "疼痛、眩晕或胸闷时停止并咨询专业人士；先掌握动作再加重",
        "快走与关节活动 5-8 分钟", "轻走与伸展 5 分钟", "所有组保留 3-4 次余力；连续两次达上限再增加约 2.5%-5% 负荷",
        ["杯式深蹲→坐站", "跪姿俯卧撑→墙面俯卧撑", "坐姿划船→弹力带划船"], 40,
        "完成当日所列动作与组数；动作质量优先，未完成可记录部分完成"),
    "PLAN-02": ("有基础动作能力、以减脂并维持肌肉为目标的成年人", "有心血管风险或不适者先咨询专业人士；间歇运动从低强度开始",
        "有氧先逐步升速 10 分钟；力量日做轻负荷热身组", "有氧缓行 8 分钟；力量日轻走伸展",
        "力量采用双进阶；有氧先增加时长再增加强度，不用训练热量抵消全部饮食预算",
        ["慢跑→单车/快走", "深蹲→杯式深蹲", "卧推→器械推胸"], 50,
        "力量日完成所列组数；有氧日达到模板最低时长；可记录部分完成"),
    "PLAN-03": ("已有约 3-12 个月规律训练经验、希望增加肌肉容量者", "关节疼痛或动作失控时停止；不得为了凑容量牺牲动作质量",
        "动态热身 8 分钟及主动作递增热身组", "低强度走动与伸展 5 分钟",
        "主动作目标 RIR 2，孤立动作 RIR 1-2；每 4 周评估疲劳并安排减量",
        ["引体→高位下拉", "前蹲→杯式深蹲", "器械推胸→俯卧撑"], 65,
        "按模板完成有效组及最低次数；未达目标记录部分完成并复盘负荷"),
    "PLAN-04": ("训练至少 1 年、具备稳定动作与恢复条件者", "连续疲劳、疼痛或睡眠显著变差时减少训练量；不适合零基础直接跟练",
        "动态热身 10 分钟及主动作递增热身组", "低强度有氧与伸展 5-8 分钟",
        "每周总容量增加不超过约 10%；第二轮调整次数区间，疲劳积累时减量",
        ["辅助引体→高位下拉", "杠铃深蹲→腿举", "硬拉→轻负荷髋铰链"], 75,
        "完成当天主要动作和预定组次；欠缺的组按实际记录，不补造容量"),
    "PLAN-05": ("三大项技术成熟、目标为提升最大力量的高阶训练者", "高负荷训练需保护者和安全架；疼痛、眩晕或异常心率时停止，测试周不强求极限 1RM",
        "专项热身 10-15 分钟及递增热身组", "低强度走动与放松 8 分钟",
        "第 1-4 周积累、第 5-7 周强化、第 8 周减量、第 9 周技术测试；若主项 RPE 高于计划约 2 或连续两次失败，建议降重约 5%-10%，不自动改写记录",
        ["深蹲→安全杠深蹲", "卧推→哑铃卧推", "硬拉→陷阱杠硬拉"], 80,
        "记录重量、次数、RPE 与主项完成度；测试周只做技术稳定的重单次"),
    "PLAN-06": ("停训后希望低冲击恢复一般体能者", "非医疗康复处方；疼痛、眩晕或异常心率时立即停止并寻求专业意见",
        "轻步行与活动度 5-8 分钟", "慢走与呼吸放松 5 分钟",
        "控制在主观强度 RPE 4-6、无痛范围；先增加动作质量和次数，再小幅增加阻力",
        ["箱式深蹲→坐站", "低台阶→原地抬腿", "弹力带划船→轻阻力坐姿划船"], 35,
        "完成无痛范围内的所列组次；不适时停止并按实际记录部分完成"),
}


def _weekly_template(code: str, week_no: int, title: str, exercises: list[str]) -> tuple[str, list[str]]:
    if code != "PLAN-05":
        return title, exercises
    if week_no <= 4:
        return "积累 · " + title, exercises
    if week_no <= 7:
        result = list(exercises)
        result[0] = re.sub(r"([×xX])\d+(?:[-–]\d+)?", r"\g<1>3", result[0], count=1)
        return "强化 · " + title, result
    if week_no == 8:
        return "减量 · " + title, [re.sub(r"(\d+)([×xX])", lambda m: f"{max(1, int(m[1]) // 2)}{m[2]}",
                                         item, count=1) for item in exercises]
    result = list(exercises)
    result[0] = re.sub(r"\d+[×xX]\d+(?:[-–]\d+)?", "3×1", result[0], count=1)
    return "技术测试 · " + title, result


def seed() -> None:
    with transaction() as db:
        for ident,name,kcal,carb,protein,fat,fiber,allergens in FOODS:
            db.execute("""INSERT OR IGNORE INTO food_items(id,name,kcal,carb_g,protein_g,fat_g,
                fiber_g,allergens_json,verified) VALUES (?,?,?,?,?,?,?,?,1)""",
                (ident,name,kcal,carb,protein,fat,fiber,as_json(allergens)))
        for rank, (original, replacement) in enumerate(FOOD_SUBSTITUTIONS, 1):
            db.execute("""INSERT OR IGNORE INTO food_substitutions
                (from_food_id,to_food_id,rank) VALUES (?,?,?)""",
                (original, replacement, rank))
        for ident,name,scenario,minutes,ingredients,steps,parts,allergens in RECIPES:
            cost, flavors = RECIPE_METADATA[ident]
            db.execute("""INSERT OR IGNORE INTO recipes(id,name,scenario,cook_minutes,
                instructions_json,allergens_json,estimated_cost_cny,flavors_json)
                VALUES (?,?,?,?,?,?,?,?)""",
                (ident,name,scenario,minutes,as_json(steps),as_json(allergens),cost,as_json(flavors)))
            # Backfill seeded recipes when migrating a database created before 002.
            db.execute("""UPDATE recipes SET estimated_cost_cny=?,flavors_json=?
                WHERE id=? AND source='official'""", (cost, as_json(flavors), ident))
            for food_id,grams in parts:
                db.execute("""INSERT OR IGNORE INTO recipe_ingredients(recipe_id,food_id,amount,unit,grams)
                    VALUES (?,?,?,?,?)""", (ident,food_id,grams,"g",grams))
        for code,name,level,goal,weeks,days,description,plan_days in PLANS:
            prior = db.execute("SELECT version FROM training_plans WHERE id=? AND code=?",
                               (code, code)).fetchone()
            db.execute("""INSERT OR IGNORE INTO training_plans(id,code,name,level,goal_type,weeks,
                days_per_week,description) VALUES (?,?,?,?,?,?,?,?)""",
                (code,code,name,level,goal,weeks,days,description))
            existing = db.execute("SELECT version FROM training_plans WHERE id=? AND code=?",
                                  (code, code)).fetchone()
            if existing is None or existing[0] >= 2:
                continue
            if prior is not None:
                db.execute("""INSERT OR IGNORE INTO official_plan_template_history
                    (plan_id,version,plan_day_id,week_no,day_no,title,session_template_json)
                    SELECT plan_id,?,id,week_no,day_no,title,session_template_json
                    FROM plan_days WHERE plan_id=?""", (prior[0], code))
            suitability,contraindications,warmup,cooldown,progression,alternatives,minutes,completion = PLAN_DETAILS[code]
            db.execute("""UPDATE training_plans SET name=?,level=?,goal_type=?,weeks=?,days_per_week=?,
                description=?,suitability=?,contraindications=?,warmup=?,cooldown=?,
                progression_rule=?,alternatives_json=?,estimated_minutes=?,completion_rule=?,version=2
                WHERE id=? AND code=? AND version<2""",
                (name,level,goal,weeks,days,description,suitability,contraindications,warmup,
                 cooldown,progression,as_json(alternatives),minutes,completion,code,code))
            for day_no,title,exercises in plan_days:
                for week_no in range(1,weeks+1):
                    week_title, week_exercises = _weekly_template(code, week_no, title, exercises)
                    db.execute("""INSERT INTO plan_days(id,plan_id,week_no,day_no,title,
                        session_template_json) VALUES (?,?,?,?,?,?)
                        ON CONFLICT(id) DO UPDATE SET title=excluded.title,
                        session_template_json=excluded.session_template_json""",
                        (f"{code}-{week_no}-{day_no}",code,week_no,day_no,
                         week_title,as_json(week_exercises)))
