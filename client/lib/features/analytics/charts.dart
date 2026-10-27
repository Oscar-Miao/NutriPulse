import 'dart:math';
import 'package:flutter/material.dart';
import '../../core/data.dart';
import '../../ui/design.dart';

void chartText(
  Canvas canvas,
  String text,
  Offset offset, {
  Color color = P.muted,
}) {
  final painter = TextPainter(
    text: TextSpan(
      text: text,
      style: TextStyle(fontSize: 9, color: color),
    ),
    textDirection: TextDirection.ltr,
  )..layout();
  painter.paint(canvas, offset);
}

class EnergyPainter extends CustomPainter {
  final List<Json> points;
  EnergyPainter(this.points);
  @override
  void paint(Canvas canvas, Size size) {
    if (points.isEmpty) {
      chartText(canvas, '暂无记录', const Offset(20, 50));
      return;
    }
    final rect = Rect.fromLTRB(35, 15, size.width - 8, size.height - 25),
        zero = rect.center.dy;
    var maximum = 1.0;
    for (final p in points) {
      for (final key in [
        'intake_kcal',
        'expenditure_kcal',
        'bmr_kcal',
        'net_kcal',
      ]) {
        maximum = max(maximum, p.n(key).abs());
      }
    }
    final scale = (rect.height / 2 - 5) / maximum;
    canvas.drawLine(
      Offset(rect.left, zero),
      Offset(rect.right, zero),
      Paint()
        ..color = P.line
        ..strokeWidth = 1,
    );
    chartText(canvas, display(maximum), Offset(0, rect.top));
    chartText(canvas, '0', Offset(13, zero - 5));
    chartText(canvas, '-${display(maximum)}', Offset(0, rect.bottom - 9));
    final step = rect.width / points.length, width = min(14.0, step * .6);
    Offset? previousNet, previousBmr;
    for (var i = 0; i < points.length; i++) {
      final p = points[i], x = rect.left + step * (i + .5);
      canvas.drawRRect(
        RRect.fromRectAndRadius(
          Rect.fromLTRB(
            x - width / 2,
            zero - p.n('intake_kcal') * scale,
            x + width / 2,
            zero,
          ),
          const Radius.circular(2),
        ),
        Paint()..color = P.green,
      );
      if (p['expenditure_kcal'] != null) {
        canvas.drawRRect(
          RRect.fromRectAndRadius(
            Rect.fromLTRB(
              x - width / 2,
              zero,
              x + width / 2,
              zero + p.n('expenditure_kcal') * scale,
            ),
            const Radius.circular(2),
          ),
          Paint()..color = P.red.withValues(alpha: .7),
        );
      }
      final net = p['net_kcal'] == null
          ? null
          : Offset(x, zero - p.n('net_kcal') * scale);
      if (net != null) {
        if (previousNet != null) {
          canvas.drawLine(
            previousNet,
            net,
            Paint()
              ..color = P.yellow
              ..strokeWidth = 2,
          );
        }
        canvas.drawCircle(net, 2.5, Paint()..color = P.yellow);
      }
      previousNet = net;
      final bmr = p['bmr_kcal'] == null
          ? null
          : Offset(x, zero + p.n('bmr_kcal') * scale);
      if (bmr != null) {
        if (previousBmr != null) {
          final length = (bmr - previousBmr).distance;
          for (double d = 0; d < length; d += 8) {
            canvas.drawLine(
              Offset.lerp(previousBmr, bmr, d / length)!,
              Offset.lerp(previousBmr, bmr, min(d + 4, length) / length)!,
              Paint()
                ..color = P.blue
                ..strokeWidth = 1.5,
            );
          }
        }
        canvas.drawCircle(bmr, 2, Paint()..color = P.blue);
      }
      previousBmr = bmr;
      if (i == 0 ||
          i == points.length - 1 ||
          (points.length > 5 && i % (points.length ~/ 4) == 0)) {
        final label = p.s('period');
        chartText(
          canvas,
          label.length > 5 ? label.substring(5) : label,
          Offset((x - 12).clamp(rect.left, rect.right - 28), rect.bottom + 7),
        );
      }
    }
  }

  @override
  bool shouldRepaint(covariant EnergyPainter old) => old.points != points;
}

class TrendLine {
  final String field, label;
  final Color color;
  final bool right;
  const TrendLine(this.field, this.label, this.color, {this.right = false});
}

class TrendPainter extends CustomPainter {
  final List<Json> points;
  final List<TrendLine> lines;
  TrendPainter(this.points, this.lines);
  @override
  void paint(Canvas canvas, Size size) {
    final rect = Rect.fromLTRB(32, 20, size.width - 35, size.height - 23);
    canvas.drawLine(rect.bottomLeft, rect.bottomRight, Paint()..color = P.line);
    if (points.isEmpty ||
        !points.any((p) => lines.any((line) => p[line.field] != null))) {
      chartText(canvas, '暂无测量或训练记录', Offset(rect.left, rect.center.dy));
      return;
    }
    for (final line in lines) {
      final values = points
          .where((p) => p[line.field] != null)
          .map((p) => p.n(line.field))
          .toList();
      if (values.isEmpty) continue;
      final maximum = max(1.0, values.reduce(max) * 1.12);
      chartText(
        canvas,
        display(maximum),
        Offset(line.right ? rect.right + 3 : 0, rect.top),
        color: line.color,
      );
      chartText(
        canvas,
        '0',
        Offset(line.right ? rect.right + 3 : 14, rect.bottom - 9),
        color: line.color,
      );
      Offset? previous;
      for (var i = 0; i < points.length; i++) {
        if (points[i][line.field] == null) {
          previous = null;
          continue;
        }
        final x =
            rect.left +
            rect.width * (points.length == 1 ? .5 : i / (points.length - 1));
        final point = Offset(
          x,
          rect.bottom - rect.height * points[i].n(line.field) / maximum,
        );
        if (previous != null) {
          canvas.drawLine(
            previous,
            point,
            Paint()
              ..color = line.color
              ..strokeWidth = 2,
          );
        }
        canvas.drawCircle(point, 3, Paint()..color = line.color);
        previous = point;
      }
    }
    if (points.isNotEmpty) {
      chartText(
        canvas,
        points.first.s('week'),
        Offset(rect.left, rect.bottom + 5),
      );
      chartText(
        canvas,
        points.last.s('week'),
        Offset(rect.right - 45, rect.bottom + 5),
      );
    }
  }

  @override
  bool shouldRepaint(covariant TrendPainter old) =>
      old.points != points || old.lines != lines;
}
