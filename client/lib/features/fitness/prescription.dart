class Prescription {
  final String name;
  final int sets, amount;
  final bool timed;
  const Prescription(this.name, this.sets, this.amount, this.timed);
  factory Prescription.parse(String text) {
    final m = RegExp(
      r'^(.*?)\s+(\d+)[×xX](\d+)(?:[-–]\d+)?.*$',
    ).firstMatch(text);
    return Prescription(
      m?.group(1)?.trim() ?? text,
      (m == null ? 1 : int.parse(m.group(2)!)).clamp(1, 8),
      m == null ? 8 : int.parse(m.group(3)!),
      RegExp(r'\d+\s*秒(?:/侧)?$').hasMatch(text),
    );
  }
}
