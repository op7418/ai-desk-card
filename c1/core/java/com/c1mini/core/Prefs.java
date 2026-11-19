package com.c1mini.core;

import android.content.Context;
import android.content.SharedPreferences;

/** 每个 APK 一份独立偏好，互不干扰；键名两边各自约定，公共的那几个见 Books/Config 注释 */
public final class Prefs {
    private static SharedPreferences sp;

    private Prefs() {
    }

    public static void init(Context c, String name) {
        if (sp == null) sp = c.getApplicationContext().getSharedPreferences(name, Context.MODE_PRIVATE);
    }

    public static SharedPreferences get() {
        return sp;
    }

    public static int i(String key, int def) {
        return sp == null ? def : sp.getInt(key, def);
    }

    public static float f(String key, float def) {
        return sp == null ? def : sp.getFloat(key, def);
    }

    public static boolean b(String key, boolean def) {
        return sp == null ? def : sp.getBoolean(key, def);
    }

    public static String s(String key, String def) {
        return sp == null ? def : sp.getString(key, def);
    }

    public static void put(String key, int v) {
        if (sp != null) sp.edit().putInt(key, v).apply();
    }

    public static void put(String key, float v) {
        if (sp != null) sp.edit().putFloat(key, v).apply();
    }

    public static void put(String key, boolean v) {
        if (sp != null) sp.edit().putBoolean(key, v).apply();
    }

    public static void put(String key, String v) {
        if (sp != null) sp.edit().putString(key, v).apply();
    }

    public static void remove(String key) {
        if (sp != null) sp.edit().remove(key).apply();
    }
}
