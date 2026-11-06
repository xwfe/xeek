import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart';

/// keex 的秘密输入框：forui 的普通输入框，加上发给系统输入法和自动填充服务的配置。
///
/// 不直接用 `FTextField.password`，原因有两个：
/// - 它的 autofillHints 不能为 null，默认是“密码”。Flutter 只有收到 null 才关自动填充，
///   空列表照样把字段报给系统的自动填充服务；在保险柜里编辑条目时，别的密码管理器会提示“保存这个密码”。
/// - 它默认允许输入法个性化学习，Android 输入法可能把输入内容记进词库。
class KeexSecretField extends StatefulWidget {
  const KeexSecretField({super.key, required this.label, required this.initial});

  final String label;
  final String initial;

  @override
  State<KeexSecretField> createState() => _KeexSecretFieldState();
}

class _KeexSecretFieldState extends State<KeexSecretField> {
  bool hidden = true;

  @override
  Widget build(BuildContext context) => FTextField(
    label: Text(widget.label),
    control: FTextFieldControl.managed(initial: TextEditingValue(text: widget.initial)),
    obscureText: hidden,
    // 遮住时用普通键盘类型，Flutter 会因为 obscureText 报成 Android 的 password；
    // 一直写 visiblePassword 的话，遮住时系统拿到的也是“可见密码”。
    keyboardType: hidden ? TextInputType.text : TextInputType.visiblePassword,
    autocorrect: false,
    enableSuggestions: false,
    enableIMEPersonalizedLearning: false,
    smartDashesType: SmartDashesType.disabled,
    smartQuotesType: SmartQuotesType.disabled,
    autofillHints: null,
    // forui 自带的显示按钮只有 40×40，iOS 44pt 和 Android 48dp 都不够，这里换成 48×48 的 lg 尺寸。
    suffixBuilder: (context, style, variants) => Padding(
      padding: style.obscureButtonPadding,
      child: FButton.icon(
        variant: .ghost,
        size: .lg,
        semanticsLabel: hidden ? '显示${widget.label}' : '隐藏${widget.label}',
        onPress: () => setState(() => hidden = !hidden),
        child: Icon(hidden ? FLucideIcons.eye : FLucideIcons.eyeOff),
      ),
    ),
  );
}

/// 动态口令：默认遮住，读屏只听到“已隐藏”，用户点了显示才读出数字。
class OtpPreview extends StatefulWidget {
  const OtpPreview({super.key, required this.code});

  final String code;

  @override
  State<OtpPreview> createState() => _OtpPreviewState();
}

class _OtpPreviewState extends State<OtpPreview> {
  bool hidden = true;

  @override
  Widget build(BuildContext context) {
    final grouped = '${widget.code.substring(0, 3)} ${widget.code.substring(3)}';
    return FCard(
      child: Row(
        children: [
          Expanded(
            child: Semantics(
              label: hidden ? '动态口令，已隐藏' : '动态口令',
              value: hidden ? null : grouped,
              excludeSemantics: true,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('动态口令', style: context.theme.typography.body.sm),
                  Text(
                    hidden ? '••• •••' : grouped,
                    style: context.theme.typography.display.xl2.copyWith(
                      fontFeatures: const [FontFeature.tabularFigures()],
                    ),
                  ),
                ],
              ),
            ),
          ),
          FButton.icon(
            size: .lg,
            semanticsLabel: hidden ? '显示动态口令' : '隐藏动态口令',
            onPress: () => setState(() => hidden = !hidden),
            child: Icon(hidden ? FLucideIcons.eye : FLucideIcons.eyeOff),
          ),
        ],
      ),
    );
  }
}
