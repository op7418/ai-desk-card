#include "widgets.h"

WidgetEntry g_widgets[SLOT_COUNT] = {};
uint16_t    g_widget_gen          = 0;

namespace {

WidgetType typeFromString(const char* s) {
    if (!s) return WIDGET_NONE;
    if (strcmp(s, "weather")     == 0) return WIDGET_WEATHER;
    if (strcmp(s, "todo")        == 0) return WIDGET_TODO;
    if (strcmp(s, "calendar")    == 0) return WIDGET_CALENDAR;
    if (strcmp(s, "messages")    == 0) return WIDGET_MESSAGES;
    if (strcmp(s, "ai-status")   == 0) return WIDGET_AI_STATUS;
    if (strcmp(s, "ai-tasks")    == 0) return WIDGET_AI_TASKS;
    if (strcmp(s, "scratch")     == 0) return WIDGET_SCRATCH;
    if (strcmp(s, "focus")       == 0) return WIDGET_FOCUS;
    if (strcmp(s, "now-playing") == 0) return WIDGET_NOW_PLAYING;
    if (strcmp(s, "git-status")  == 0) return WIDGET_GIT_STATUS;
    if (strcmp(s, "system")      == 0) return WIDGET_SYSTEM;
    return WIDGET_NONE;
}

WidgetSlot slotFromString(const char* s) {
    if (!s) return SLOT_COUNT;
    if (strcmp(s, "top-left")  == 0) return SLOT_TOP_LEFT;
    if (strcmp(s, "top-right") == 0) return SLOT_TOP_RIGHT;
    if (strcmp(s, "middle")    == 0) return SLOT_MIDDLE;
    if (strcmp(s, "bottom")    == 0) return SLOT_BOTTOM;
    if (strcmp(s, "full")      == 0) return SLOT_FULL;
    return SLOT_COUNT;
}

uint8_t todoTagFromString(const char* s) {
    if (!s) return 0;
    if (strcmp(s, "overdue")   == 0) return 1;
    if (strcmp(s, "today")     == 0) return 2;
    if (strcmp(s, "tomorrow")  == 0) return 3;
    if (strcmp(s, "this-week") == 0) return 4;
    if (strcmp(s, "later")     == 0) return 5;
    return 0;
}

void copyStr(char* dst, size_t cap, const char* src) {
    if (!src) { dst[0] = 0; return; }
    strncpy(dst, src, cap - 1);
    dst[cap - 1] = 0;
}

void parseWeather(JsonObject d, WidgetWeatherData& w) {
    copyStr(w.location, sizeof(w.location), d["location"] | "");
    JsonObject cur = d["current"];
    w.has_current = !cur.isNull();
    if (w.has_current) {
        w.current_temp = (int16_t)(cur["temp_c"] | 0.0f);
        copyStr(w.current_condition, sizeof(w.current_condition),
                cur["condition"] | "");
    }
    JsonArray fc = d["forecast"];
    w.forecast_count = 0;
    if (!fc.isNull()) {
        for (JsonVariant v : fc) {
            if (w.forecast_count >= WIDGET_MAX_FORECAST) break;
            JsonObject o = v.as<JsonObject>();
            if (o.isNull()) continue;
            WidgetWeatherForecast& f = w.forecast[w.forecast_count++];
            copyStr(f.day, sizeof(f.day), o["day"] | "");
            f.high = (int16_t)(o["high"] | 0.0f);
            f.low  = (int16_t)(o["low"]  | 0.0f);
            copyStr(f.condition, sizeof(f.condition), o["condition"] | "");
        }
    }
}

void parseTodo(JsonObject d, WidgetTodoData& t) {
    copyStr(t.title, sizeof(t.title), d["title"] | "");
    JsonArray items = d["items"];
    t.item_count = 0;
    if (!items.isNull()) {
        for (JsonVariant v : items) {
            if (t.item_count >= WIDGET_MAX_TODO_ITEMS) break;
            JsonObject o = v.as<JsonObject>();
            if (o.isNull()) continue;
            WidgetTodoItem& it = t.items[t.item_count++];
            copyStr(it.text, sizeof(it.text), o["text"] | "");
            copyStr(it.due,  sizeof(it.due),  o["due"]  | "");
            it.tag = todoTagFromString(o["tag"] | "");
        }
    }
}

void parseCalendar(JsonObject d, WidgetCalendarData& tl) {
    const char* now_iso = d["now_iso"] | "";
    if (strlen(now_iso) >= 16) {
        memcpy(tl.now_label, now_iso + 11, 5);
        tl.now_label[5] = 0;
    } else {
        tl.now_label[0] = 0;
    }
    JsonArray events = d["events"];
    tl.event_count = 0;
    if (!events.isNull()) {
        for (JsonVariant v : events) {
            if (tl.event_count >= WIDGET_MAX_CALENDAR) break;
            JsonObject o = v.as<JsonObject>();
            if (o.isNull()) continue;
            WidgetCalendarEvent& ev = tl.events[tl.event_count++];
            copyStr(ev.start, sizeof(ev.start), o["start"] | "");
            copyStr(ev.end,   sizeof(ev.end),   o["end"]   | "");
            copyStr(ev.title, sizeof(ev.title), o["title"] | "");
        }
    }
}

void parseMessages(JsonObject d, WidgetMessagesData& m) {
    JsonArray items = d["items"];
    m.count = 0;
    if (!items.isNull()) {
        for (JsonVariant v : items) {
            if (m.count >= WIDGET_MAX_MESSAGES) break;
            JsonObject o = v.as<JsonObject>();
            if (o.isNull()) continue;
            WidgetMessage& it = m.items[m.count++];
            copyStr(it.sender,  sizeof(it.sender),  o["sender"]  | "");
            copyStr(it.preview, sizeof(it.preview), o["preview"] | "");
            copyStr(it.age,     sizeof(it.age),     o["age"]     | "");
        }
    }
}

void parseAiStatus(JsonObject d, WidgetAiStatusData& a) {
    copyStr(a.session_name, sizeof(a.session_name), d["session_name"] | "");
    copyStr(a.model,        sizeof(a.model),        d["model"]        | "");
    copyStr(a.task,         sizeof(a.task),         d["task"]         | "");
    JsonObject ctx = d["context"];
    a.ctx_used  = ctx.isNull() ? 0 : (uint32_t)(ctx["used"]  | 0);
    a.ctx_limit = ctx.isNull() ? 0 : (uint32_t)(ctx["limit"] | 0);
    copyStr(a.last_message_preview, sizeof(a.last_message_preview),
            d["last_message_preview"] | "");
    a.elapsed_seconds = (uint32_t)(d["elapsed_seconds"] | 0);
}

void parseAiTasks(JsonObject d, WidgetAiTasksData& t) {
    t.running         = (uint16_t)(d["running"]         | 0);
    t.waiting         = (uint16_t)(d["waiting"]         | 0);
    t.blocked         = (uint16_t)(d["blocked"]         | 0);
    t.completed_today = (uint16_t)(d["completed_today"] | 0);
}

void parseScratch(JsonObject d, WidgetScratchData& s) {
    copyStr(s.text,   sizeof(s.text),   d["text"]   | "");
    copyStr(s.source, sizeof(s.source), d["source"] | "");
    copyStr(s.age,    sizeof(s.age),    d["age"]    | "");
}

void parseFocus(JsonObject d, WidgetFocusData& f) {
    copyStr(f.task,     sizeof(f.task),     d["task"]     | "");
    copyStr(f.big_text, sizeof(f.big_text), d["big_text"] | "");
    copyStr(f.subtitle, sizeof(f.subtitle), d["subtitle"] | "");
    f.pomodoros_done    = (uint8_t)(d["pomodoros_done"]    | 0);
    f.pomodoros_planned = (uint8_t)(d["pomodoros_planned"] | 0);
}

void parseNowPlaying(JsonObject d, WidgetNowPlayingData& n) {
    copyStr(n.track,  sizeof(n.track),  d["track"]  | "");
    copyStr(n.artist, sizeof(n.artist), d["artist"] | "");
    copyStr(n.source, sizeof(n.source), d["source"] | "");
    n.position_sec = (uint32_t)(d["position_sec"] | 0);
    n.duration_sec = (uint32_t)(d["duration_sec"] | 0);
    n.playing      = d["playing"] | true;
}

void parseGitStatus(JsonObject d, WidgetGitStatusData& g) {
    copyStr(g.repo_name,        sizeof(g.repo_name),        d["repo_name"]        | "");
    copyStr(g.branch,           sizeof(g.branch),           d["branch"]           | "");
    g.modified  = (uint16_t)(d["modified"]  | 0);
    g.untracked = (uint16_t)(d["untracked"] | 0);
    g.staged    = (uint16_t)(d["staged"]    | 0);
    g.ahead     = (int16_t)( d["ahead"]     | 0);
    g.behind    = (int16_t)( d["behind"]    | 0);
    copyStr(g.last_commit_hash, sizeof(g.last_commit_hash), d["last_commit_hash"] | "");
    copyStr(g.last_commit_msg,  sizeof(g.last_commit_msg),  d["last_commit_msg"]  | "");
}

void parseSystem(JsonObject d, WidgetSystemData& s) {
    s.cpu_pct      = (uint8_t)( d["cpu_pct"]      | 0);
    s.memory_pct   = (uint8_t)( d["memory_pct"]   | 0);
    s.disk_pct     = (uint8_t)( d["disk_pct"]     | 0);
    s.battery_pct  = (uint8_t)( d["battery_pct"]  | 0xFF);   // 0xFF = no battery
    s.net_down_kbps = (uint32_t)(d["net_down_kbps"] | 0);
    s.net_up_kbps   = (uint32_t)(d["net_up_kbps"]   | 0);
    s.temp_c        = (int16_t)(d["temp_c"]        | INT16_MIN);
}

}  // namespace

bool widgetsHandleCommand(JsonDocument& doc) {
    const char* cmd = doc["cmd"];
    if (!cmd) return false;

    if (strcmp(cmd, "widget_set") == 0) {
        for (uint8_t i = 0; i < SLOT_COUNT; i++) g_widgets[i].type = WIDGET_NONE;

        JsonArray widgets = doc["widgets"];
        if (!widgets.isNull()) {
            for (JsonVariant v : widgets) {
                JsonObject w = v.as<JsonObject>();
                if (w.isNull()) continue;
                WidgetSlot slot = slotFromString(w["slot"] | "");
                WidgetType type = typeFromString(w["type"] | "");
                if (slot >= SLOT_COUNT || type == WIDGET_NONE) continue;
                WidgetEntry& e = g_widgets[slot];
                e.type       = type;
                e.stale      = w["stale"] | false;
                e.updated_ms = millis();
                JsonObject d = w["data"];
                if (d.isNull()) continue;
                switch (type) {
                    case WIDGET_WEATHER:     parseWeather(d, e.weather);          break;
                    case WIDGET_TODO:        parseTodo(d, e.todo);                break;
                    case WIDGET_CALENDAR:    parseCalendar(d, e.calendar);        break;
                    case WIDGET_MESSAGES:    parseMessages(d, e.messages);        break;
                    case WIDGET_AI_STATUS:   parseAiStatus(d, e.ai_status);       break;
                    case WIDGET_AI_TASKS:    parseAiTasks(d, e.ai_tasks);         break;
                    case WIDGET_SCRATCH:     parseScratch(d, e.scratch);          break;
                    case WIDGET_FOCUS:       parseFocus(d, e.focus);              break;
                    case WIDGET_NOW_PLAYING: parseNowPlaying(d, e.now_playing);   break;
                    case WIDGET_GIT_STATUS:  parseGitStatus(d, e.git_status);     break;
                    case WIDGET_SYSTEM:      parseSystem(d, e.system);            break;
                    default: break;
                }
            }
        }
        g_widget_gen++;
        return true;
    }

    return false;
}
