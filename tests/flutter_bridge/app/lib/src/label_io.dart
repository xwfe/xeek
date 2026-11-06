String? platformLabel() {
  const label = String.fromEnvironment('KEEX_AUTO');
  return label.isEmpty ? null : label;
}
