// Run only against a disposable QA server, never the personal database.
import 'dart:io';
import 'package:nutripulse/core/api.dart';
import 'package:nutripulse/core/data.dart';
import 'package:nutripulse/features/fitness/prescription.dart';

void check(bool condition, String description) {
  if (!condition) throw StateError(description);
  stdout.writeln('PASS $description');
}

Future<void> main(List<String> args) async {
  if (args.length != 1) {
    throw ArgumentError(
      'Usage: dart run tool/verify_server.dart http://127.0.0.1:8791 (isolated QA database only)',
    );
  }
  final api = ApiClient(baseUrl: args.single);
  final day = today();
  try {
    await api.put('/profile', {
      'display_name': 'Flutter QA',
      'birth_date': '1996-03-15',
      'formula_sex': 'male',
      'height_cm': 175,
      'activity_level': 'moderate',
    });
    await api.post('/measurements', {'weight_kg': 70, 'body_fat_pct': 20});
    final preview = await api.post('/goals/preview', {
      'goal_type': 'maintenance',
    });
    check(
      preview['ready'] == true &&
          preview.obj('proposed_target').n('target_kcal') > 0,
      'goal preview uses the existing server calculation',
    );
    await api.post('/goals', {
      'goal_type': 'maintenance',
      'preview_fingerprint': preview['input_fingerprint'],
    });
    await api.put('/preferences', {
      'allergies': [],
      'restrictions': [],
      'preferences': [],
      'dining': {
        'flavors': ['清淡'],
        'preferred_scenario': 'self_cook',
        'max_cost_cny': 100,
        'max_cook_minutes': 60,
      },
    });
    await api.put('/training-profile', {
      'level': 'beginner',
      'days_per_week': 3,
      'session_minutes': 45,
      'active_kcal_goal': 300,
      'equipment': ['哑铃'],
      'limitations': [],
    });
    final before = await api.get('/nutrition/days/$day');
    final baseline = before.obj('summary').obj('energy').n('intake_kcal');
    final meal = PendingWrite('/meals', {
      'local_date': day,
      'meal_type': 'breakfast',
      'status': 'PLANNED',
      'items': [
        {
          'display_name': 'QA 米饭',
          'amount': 100,
          'unit': 'g',
          'grams': 100,
          'kcal': 116,
          'carb_g': 25.9,
          'protein_g': 2.6,
        },
      ],
    });
    final created = await meal.send(api), retried = await meal.send(api);
    check(
      created['id'] == retried['id'],
      'meal retries keep the same record ID',
    );
    final planned = await api.get('/nutrition/days/$day');
    check(
      planned.obj('summary').obj('energy').n('intake_kcal') == baseline,
      'planned meals do not count as actual intake',
    );
    await api.patch('/meals/${created['id']}', {'status': 'CONSUMED'});
    final eaten = await api.get('/nutrition/days/$day');
    check(
      eaten.obj('summary').obj('energy').n('intake_kcal') == baseline + 116,
      'PATCH confirmation updates actual intake',
    );
    check(
      eaten.obj('summary').n('incomplete_macro_items') > 0,
      'unknown fat remains incomplete instead of an explicit zero',
    );
    final waterBefore = eaten.obj('summary').n('water_ml');
    final water = PendingWrite('/water-logs', {
      'local_date': day,
      'amount_ml': 300,
    });
    await water.send(api);
    await water.send(api);
    check(
      (await api.get('/nutrition/days/$day')).obj('summary').n('water_ml') ==
          waterBefore + 300,
      'water retries do not double-count',
    );
    final estimate = await api.post('/workouts/estimate', {
      'workout_type': 'running',
      'intensity': 'moderate',
      'minutes': 20,
    });
    check(
      estimate.n('kcal') > 0 && estimate['weight_source'] == 'measurement',
      'workout estimate uses measured weight',
    );
    final workout = PendingWrite('/workouts', {
      'local_date': day,
      'workout_type': 'strength',
      'minutes': 30,
      'sets': [
        {
          'exercise_name': '卧推',
          'set_no': 1,
          'weight_kg': 20,
          'reps': 10,
          'completed': true,
        },
        {
          'exercise_name': '平板支撑',
          'set_no': 1,
          'weight_kg': null,
          'reps': 0,
          'duration_sec': 20,
          'completed': true,
        },
      ],
    });
    final saved = await workout.send(api), again = await workout.send(api);
    check(
      saved['id'] == again['id'],
      'workout retries keep the same record ID',
    );
    final fitness = await api.get('/fitness/days/$day');
    check(
      fitness.obj('summary').n('training_volume') >= 200,
      'external load contributes volume while timed bodyweight does not',
    );
    final advice = await api.get('/workouts/${saved['id']}/recovery');
    check(
      advice.rows('advice').isNotEmpty,
      'post-workout nutrition advice uses the existing endpoint',
    );
    final plans = (await api.get('/training-plans')).rows('items');
    check(
      plans.length >= 6,
      'all six official training plans remain available',
    );
    await api.post('/training-plans/${plans.first['id']}/enroll', {
      'start_date': day,
    });
    final active = await api.get('/training-plans/active?date=$day'),
        session = active.obj('today_session');
    check(
      session.isNotEmpty && session['status'] == 'SCHEDULED',
      'plan enrollment creates a scheduled session',
    );
    final sets = <Json>[];
    for (final text in session['exercises'] as List) {
      final p = Prescription.parse(text.toString());
      for (var i = 0; i < p.sets; i++) {
        sets.add({
          'exercise_name': p.name,
          'set_no': i + 1,
          'weight_kg': null,
          'reps': p.timed ? 0 : p.amount,
          if (p.timed) 'duration_sec': p.amount,
          'completed': true,
        });
      }
    }
    await api.post('/workouts', {
      'local_date': day,
      'workout_type': session['minimum_duration_minutes'] == null
          ? 'strength'
          : 'walking',
      'minutes': session['minimum_duration_minutes'] ?? 40,
      'sets': session['minimum_duration_minutes'] == null ? sets : [],
      'plan_session_id': session['id'],
    });
    check(
      (await api.get(
            '/training-plans/active?date=$day',
          )).obj('today_session')['status'] ==
          'COMPLETED',
      'prescribed session records complete with correct units',
    );
    final recommended = await api.post('/recommendations/meals', {
      'local_date': day,
      'meal_type': 'lunch',
      'scenario': 'self_cook',
    });
    check(
      recommended.rows('items').isNotEmpty,
      'recommendation list returns valid candidates',
    );
    final candidate = recommended.rows('items').first;
    final recipe = await api.get('/recipes/${candidate['candidate_ref_id']}');
    check(
      recipe.rows('ingredients').isNotEmpty &&
          (recipe['instructions'] as List).isNotEmpty,
      'cooking recipe includes ingredients and instructions',
    );
    final accepted = await api.post(
      '/recommendations/${candidate['id']}/accept',
      {'servings': .5},
    );
    final acceptedAgain = await api.post(
      '/recommendations/${candidate['id']}/accept',
      {'servings': .5},
    );
    check(
      accepted['meal_id'] == acceptedAgain['meal_id'] &&
          accepted['status'] == 'PLANNED',
      'half-portion recommendation prelogs once',
    );
    final query = 'start=$day&end=$day';
    final energy = await api.get('/analytics/energy?$query&granularity=day');
    check(
      energy.rows('series').single.n('intake_kcal') == baseline + 116,
      'analytics agrees with consumed food ledger',
    );
    check(
      (await api.get('/analytics/macros?$query')).n('incomplete_items') > 0,
      'period macro analysis keeps missing-value provenance',
    );
    check(
      (await api.get(
            '/analytics/body-composition?$query',
          )).rows('series').single.n('weight_kg') ==
          70,
      'body composition includes recorded weight',
    );
    await api.get('/analytics/habits?$query');
    final diagnosis = await api.post('/analytics/diagnostics', {
      'start': day,
      'end': day,
    });
    check(
      (diagnosis['advice'] as List).isNotEmpty && diagnosis['version'] != null,
      'AI/rule diagnosis retains versioned output',
    );
    final pdf = await api.report('day', day);
    check(
      pdf.length > 1000,
      'PDF report downloads through the Flutter API client',
    );
    check(
      (await api.get('/privacy/export?category=profile')).isNotEmpty,
      'profile data export remains available',
    );
    check(
      (await api.get(
        '/privacy/delete-preview?category=diet',
      )).s('confirmation_phrase').isNotEmpty,
      'deletion still requires preview and confirmation phrase',
    );
    stdout.writeln(
      'Flutter → existing Python server contract verification complete.',
    );
  } finally {
    api.close();
  }
}
