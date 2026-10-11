package io.github.syb1v.wdsime;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.inputmethodservice.InputMethodService;
import android.os.Build;
import android.util.Base64;
import android.view.KeyEvent;
import android.view.View;
import android.view.inputmethod.InputConnection;

import java.io.UnsupportedEncodingException;

/**
 * Тихая IME: без экранного интерфейса, принимает текст по broadcast.
 */
public class WdsIme extends InputMethodService {
    private static final String ACTION_TEXT = "io.github.syb1v.wdsime.INPUT_TEXT";
    private static final String ACTION_B64 = "io.github.syb1v.wdsime.INPUT_B64";
    private static final String ACTION_CODE = "io.github.syb1v.wdsime.INPUT_CODE";
    private static final String ACTION_CLEAR = "io.github.syb1v.wdsime.CLEAR_TEXT";

    private BroadcastReceiver receiver;

    @Override
    public void onCreate() {
        super.onCreate();
        receiver = new BroadcastReceiver() {
            @Override
            public void onReceive(Context context, Intent intent) {
                if (intent == null) {
                    return;
                }
                InputConnection ic = getCurrentInputConnection();
                if (ic == null) {
                    return;
                }
                String action = intent.getAction();
                if (action == null) {
                    return;
                }
                if (ACTION_TEXT.equals(action)) {
                    String msg = intent.getStringExtra("msg");
                    if (msg != null && !msg.isEmpty()) {
                        ic.commitText(msg, 1);
                    }
                } else if (ACTION_B64.equals(action)) {
                    String data = intent.getStringExtra("msg");
                    if (data != null) {
                        try {
                            byte[] raw = Base64.decode(data, Base64.DEFAULT);
                            ic.commitText(new String(raw, "UTF-8"), 1);
                        } catch (RuntimeException | UnsupportedEncodingException ignored) {
                        }
                    }
                } else if (ACTION_CODE.equals(action)) {
                    int code = intent.getIntExtra("code", 0);
                    if (code != 0) {
                        ic.sendKeyEvent(new KeyEvent(KeyEvent.ACTION_DOWN, code));
                        ic.sendKeyEvent(new KeyEvent(KeyEvent.ACTION_UP, code));
                    }
                } else if (ACTION_CLEAR.equals(action)) {
                    ic.deleteSurroundingText(4096, 4096);
                }
            }
        };
        IntentFilter filter = new IntentFilter();
        filter.addAction(ACTION_TEXT);
        filter.addAction(ACTION_B64);
        filter.addAction(ACTION_CODE);
        filter.addAction(ACTION_CLEAR);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            registerReceiver(receiver, filter, Context.RECEIVER_EXPORTED);
        } else {
            registerReceiver(receiver, filter);
        }
    }

    @Override
    public void onDestroy() {
        if (receiver != null) {
            try {
                unregisterReceiver(receiver);
            } catch (IllegalArgumentException ignored) {
            }
            receiver = null;
        }
        super.onDestroy();
    }

    @Override
    public View onCreateInputView() {
        // без экранного интерфейса — клавиатура не показывается
        return null;
    }
}
