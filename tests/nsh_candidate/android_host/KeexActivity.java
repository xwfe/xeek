package dev.keex.nshcandidate.host;

import android.app.Activity;
import android.os.Bundle;
import android.view.WindowManager;
import com.longbridge.nsh.NshView;

/** K092 实验宿主：只经 NSH 公开嵌入接口加载随包界面，补 NSH 默认宿主缺的系统边界。 */
public final class KeexActivity extends Activity {
    private NshView view;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_SECURE);
        view = new NshView(this);
        if (!view.setGrantedCapabilities("{}")) throw new IllegalStateException("capabilities");
        setContentView(view);
        if (!view.loadAssetBundle("nsh")) throw new IllegalStateException("bundle");
    }

    /** 最近任务只让活动失去顶层恢复态，不触发 onPause，NSH 的 lifecycle() 仍是 active。 */
    @Override
    public void onTopResumedActivityChanged(boolean top) {
        super.onTopResumedActivityChanged(top);
        if (!top) view.send("keex.revoke", null);
    }

    @Override
    @SuppressWarnings("deprecation")
    public void onBackPressed() {
        if (!view.handleBack()) super.onBackPressed();
    }

    @Override
    protected void onDestroy() {
        view.destroy();
        super.onDestroy();
    }
}
