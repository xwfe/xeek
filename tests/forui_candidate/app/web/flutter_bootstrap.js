{{flutter_js}}
{{flutter_build_config}}
// Flutter Web 遇到中文默认去 fonts.gstatic.com 下载回退字体。keex 的 CSP 不放第三方字体，
// 那样中文全成方块，所以改成从本站的 fallback-fonts/ 取（mirror_fonts.mjs 负责镜像）。
_flutter.loader.load({
  config: { fontFallbackBaseUrl: "fallback-fonts/" },
});
