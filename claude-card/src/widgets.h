// Widget cache + JSON protocol parser for claude-card.
//
// Adds two widget types vs the parent v0.4 set:
//   - messages: list of recent macOS notifications / IMs (data source is
//               daemon-side; firmware only renders the array)
//   - ai-tasks: running / waiting / blocked counters with big numerals
//
// Wire protocol consumed by widgetsHandleCommand():
//
//   {"cmd":"widget_set","version":1,"widgets":[
//      {"slot":"top-left","type":"weather","data":{...},"theme":""},
//      ...
//   ]}
//
// Called from xfer_card.h's command dispatch.

#pragma once

#include <Arduino.h>
#include <ArduinoJson.h>
#include <M5EPD.h>

enum WidgetType : uint8_t {
    WIDGET_NONE = 0,
    WIDGET_WEATHER,
    WIDGET_TODO,
    WIDGET_CALENDAR,
    WIDGET_MESSAGES,
    WIDGET_AI_STATUS,
    WIDGET_AI_TASKS,
    // v0.5.1 additions — note-taking + status-glance widgets for the
    // monitor-side use case (see PLAN.md component categories).
    WIDGET_SCRATCH,
    WIDGET_FOCUS,
    WIDGET_NOW_PLAYING,
    WIDGET_GIT_STATUS,
    WIDGET_SYSTEM,
};

enum WidgetSlot : uint8_t {
    SLOT_TOP_LEFT = 0,
    SLOT_TOP_RIGHT,
    SLOT_MIDDLE,
    SLOT_BOTTOM,
    SLOT_FULL,
    SLOT_COUNT,
};

struct SlotRect { uint16_t x, y, w, h; };

// 540 × 960 panel. Top two slots and bottom two slots are equal-sized halves
// (top: side-by-side, bottom: stacked) so the 4-slot grid feels balanced
// at a glance from monitor distance. Top corner reserved (right-side, top
// 80 px) for the settings touchscreen hot zone.
static constexpr SlotRect kSlotRects[SLOT_COUNT] = {
    {  0,   0, 270, 380 },   // top-left  (work widget)
    {270,   0, 270, 380 },   // top-right (AI widget)
    {  0, 380, 540, 290 },   // middle
    {  0, 670, 540, 290 },   // bottom
    {  0,   0, 540, 960 },   // full
};

static constexpr SlotRect kSettingsHotZone = {440, 0, 100, 80};

// Cap text caches — keep on the small side to give widgets headroom for
// big fonts. Daemon Schema should enforce these maxLengths too.
static constexpr size_t WIDGET_MAX_TEXT       = 80;
static constexpr size_t WIDGET_MAX_TODO_ITEMS = 4;
static constexpr size_t WIDGET_MAX_CALENDAR   = 4;
static constexpr size_t WIDGET_MAX_MESSAGES   = 3;
static constexpr size_t WIDGET_MAX_FORECAST   = 2;

struct WidgetWeatherForecast { char day[10]; int16_t high, low; char condition[24]; };
struct WidgetWeatherData {
    char    location[24];
    bool    has_current;
    int16_t current_temp;
    char    current_condition[24];
    uint8_t forecast_count;
    WidgetWeatherForecast forecast[WIDGET_MAX_FORECAST];
};

struct WidgetTodoItem { char text[WIDGET_MAX_TEXT]; char due[20]; uint8_t tag; };
struct WidgetTodoData {
    char    title[32];
    uint8_t item_count;
    WidgetTodoItem items[WIDGET_MAX_TODO_ITEMS];
};

struct WidgetCalendarEvent { char start[6]; char end[6]; char title[64]; };
struct WidgetCalendarData {
    char    now_label[6];   // "HH:MM"
    uint8_t event_count;
    WidgetCalendarEvent events[WIDGET_MAX_CALENDAR];
};

struct WidgetMessage { char sender[24]; char preview[80]; char age[16]; };
struct WidgetMessagesData {
    uint8_t count;
    WidgetMessage items[WIDGET_MAX_MESSAGES];
};

struct WidgetAiStatusData {
    char    session_name[32];
    char    model[24];
    char    task[80];
    uint32_t ctx_used;
    uint32_t ctx_limit;
    char    last_message_preview[160];
    uint32_t elapsed_seconds;
};

struct WidgetAiTasksData {
    uint16_t running;
    uint16_t waiting;        // waiting for approval
    uint16_t blocked;        // errored / timed-out
    uint16_t completed_today;
};

// Sticky-note free-form text. AI fills `text`; `source` is "Claude" /
// "user" / a person's name; `age` is a human string like "just now" / "2h".
struct WidgetScratchData {
    char text[200];
    char source[24];
    char age[16];
};

// User's current focus task. AI passes a pre-formatted countdown string
// in `big_text` (e.g. "12:43" / "+3:00 over" / "" for no timer). Avoids
// RTC parsing + drift on device. AI is expected to re-push every ~minute
// during an active focus session — the 2 s repaint debounce + e-ink's
// nature handle the cadence gracefully. pomodoros_done/_planned drive
// the dot row at the bottom (e.g., ● ● ● ○).
struct WidgetFocusData {
    char    task[80];
    char    big_text[16];
    char    subtitle[48];
    uint8_t pomodoros_done;
    uint8_t pomodoros_planned;
};

// Now-playing track (Spotify, Apple Music, etc.). `playing` toggles the
// ⏵ / ⏸ glyph; position_sec / duration_sec drive the progress bar.
struct WidgetNowPlayingData {
    char     track[80];
    char     artist[48];
    char     source[16];
    uint32_t position_sec;
    uint32_t duration_sec;
    bool     playing;
};

// Git working-tree status of a watched repo.
struct WidgetGitStatusData {
    char    repo_name[40];
    char    branch[40];
    uint16_t modified;
    uint16_t untracked;
    uint16_t staged;
    int16_t  ahead;
    int16_t  behind;
    char     last_commit_hash[12];     // short sha
    char     last_commit_msg[60];
};

// System resources. battery_pct = 0xFF means "no battery" (desktop).
// temp_c = INT16_MIN means N/A.
struct WidgetSystemData {
    uint8_t  cpu_pct;
    uint8_t  memory_pct;
    uint8_t  disk_pct;
    uint8_t  battery_pct;
    uint32_t net_down_kbps;
    uint32_t net_up_kbps;
    int16_t  temp_c;
};

struct WidgetEntry {
    WidgetType type;
    bool       stale;
    uint32_t   updated_ms;
    union {
        WidgetWeatherData     weather;
        WidgetTodoData        todo;
        WidgetCalendarData    calendar;
        WidgetMessagesData    messages;
        WidgetAiStatusData    ai_status;
        WidgetAiTasksData     ai_tasks;
        WidgetScratchData     scratch;
        WidgetFocusData       focus;
        WidgetNowPlayingData  now_playing;
        WidgetGitStatusData   git_status;
        WidgetSystemData      system;
    };
};

extern WidgetEntry g_widgets[SLOT_COUNT];
extern uint16_t    g_widget_gen;   // bumps on every widget_set frame

// Returns true if doc was a widget_set command and was consumed.
bool widgetsHandleCommand(JsonDocument& doc);

inline bool widgetsActive() {
    for (uint8_t i = 0; i < SLOT_COUNT; i++) {
        if (g_widgets[i].type != WIDGET_NONE) return true;
    }
    return false;
}
