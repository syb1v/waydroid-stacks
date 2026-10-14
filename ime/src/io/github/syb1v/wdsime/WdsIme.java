package io.github.syb1v.wdsime;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.inputmethodservice.InputMethodService;
import android.os.Build;
import android.util.Base64;
import android.util.Log;
import android.view.KeyEvent;
import android.view.View;
import android.view.inputmethod.InputConnection;

import java.io.UnsupportedEncodingException;

/**
 * Тихая IME: без экранного интерфейса, принимает текст по broadcast.
 *
 * Дополнительно обрабатывает аппаратные клавиши (onKeyDown): у виртуальной
 * клавиатуры Waydroid нет KeyCharacterMap, поэтому буквы, цифры и пунктуация
 * переводятся в текст собственным маппингом (QWERTY + Shift). Без этого
 * «показанная» IME глотала физический ввод в текстовых полях.
 */
public class WdsIme extends InputMethodService {
    private static final String TAG = "wdsime";
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
    public boolean onKeyDown(int keyCode, KeyEvent event) {
        InputConnection ic = getCurrentInputConnection();
        if (ic == null) {
            return super.onKeyDown(keyCode, event);
        }
        // хоткеи с модификаторами не перехватываем
        if (event.isCtrlPressed() || event.isAltPressed() || event.isMetaPressed()) {
            return super.onKeyDown(keyCode, event);
        }
        switch (keyCode) {
            case KeyEvent.KEYCODE_DEL:
                ic.deleteSurroundingText(1, 0);
                return true;
            case KeyEvent.KEYCODE_FORWARD_DEL:
                ic.deleteSurroundingText(0, 1);
                return true;
            case KeyEvent.KEYCODE_ENTER:
            case KeyEvent.KEYCODE_NUMPAD_ENTER:
                ic.sendKeyEvent(new KeyEvent(KeyEvent.ACTION_DOWN, keyCode));
                ic.sendKeyEvent(new KeyEvent(KeyEvent.ACTION_UP, keyCode));
                return true;
            default:
                break;
        }
        int ch = event.getUnicodeChar(event.getMetaState());
        if (ch == 0) {
            ch = charFor(keyCode, event.isShiftPressed());
        }
        if (ch != 0) {
            ic.commitText(new String(Character.toChars(ch)), 1);
            return true;
        }
        return super.onKeyDown(keyCode, event);
    }

    @Override
    public boolean onKeyUp(int keyCode, KeyEvent event) {
        if (event.isCtrlPressed() || event.isAltPressed() || event.isMetaPressed()) {
            return super.onKeyUp(keyCode, event);
        }
        switch (keyCode) {
            case KeyEvent.KEYCODE_DEL:
            case KeyEvent.KEYCODE_FORWARD_DEL:
            case KeyEvent.KEYCODE_ENTER:
            case KeyEvent.KEYCODE_NUMPAD_ENTER:
                return true;
            default:
                break;
        }
        if (charFor(keyCode, event.isShiftPressed()) != 0) {
            return true;  // символ уже отправлен на onKeyDown
        }
        return super.onKeyUp(keyCode, event);
    }

    /** QWERTY-маппинг для клавиатуры без KeyCharacterMap (Waydroid). */
    private static int charFor(int keyCode, boolean shift) {
        if (keyCode >= KeyEvent.KEYCODE_A && keyCode <= KeyEvent.KEYCODE_Z) {
            int c = 'a' + (keyCode - KeyEvent.KEYCODE_A);
            return shift ? Character.toUpperCase(c) : c;
        }
        if (keyCode >= KeyEvent.KEYCODE_0 && keyCode <= KeyEvent.KEYCODE_9) {
            int i = keyCode - KeyEvent.KEYCODE_0;
            return shift ? ")!@#$%^&*(".charAt(i) : '0' + i;
        }
        if (keyCode >= KeyEvent.KEYCODE_NUMPAD_0 && keyCode <= KeyEvent.KEYCODE_NUMPAD_9) {
            return '0' + (keyCode - KeyEvent.KEYCODE_NUMPAD_0);
        }
        switch (keyCode) {
            case KeyEvent.KEYCODE_SPACE: return ' ';
            case KeyEvent.KEYCODE_MINUS: return shift ? '_' : '-';
            case KeyEvent.KEYCODE_EQUALS: return shift ? '+' : '=';
            case KeyEvent.KEYCODE_LEFT_BRACKET: return shift ? '{' : '[';
            case KeyEvent.KEYCODE_RIGHT_BRACKET: return shift ? '}' : ']';
            case KeyEvent.KEYCODE_BACKSLASH: return shift ? '|' : '\\';
            case KeyEvent.KEYCODE_SEMICOLON: return shift ? ':' : ';';
            case KeyEvent.KEYCODE_APOSTROPHE: return shift ? '"' : '\'';
            case KeyEvent.KEYCODE_COMMA: return shift ? '<' : ',';
            case KeyEvent.KEYCODE_PERIOD: return shift ? '>' : '.';
            case KeyEvent.KEYCODE_SLASH: return shift ? '?' : '/';
            case KeyEvent.KEYCODE_GRAVE: return shift ? '~' : '`';
            case KeyEvent.KEYCODE_AT: return '@';
            case KeyEvent.KEYCODE_STAR: return '*';
            case KeyEvent.KEYCODE_PLUS: return '+';
            case KeyEvent.KEYCODE_POUND: return '#';
            default: return 0;
        }
    }

    @Override
    public View onCreateInputView() {
        // без экранного интерфейса — клавиатура не показывается
        return null;
    }
}
