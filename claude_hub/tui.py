"""Curses-based TUI for claude-hub."""
import curses
import os
import sys

from claude_hub import config
from claude_hub import integration
from claude_hub import models as mdl
from claude_hub import updater
from claude_hub.launcher import launch

C_HEADER = 1
C_ACTIVE_TAB = 2
C_INACTIVE_TAB = 3
C_SELECTED = 4
C_DIM = 5
C_OK = 6
C_WARN = 7
C_PROVIDER = 8
C_SEARCH = 9
C_STATUS = 10


def _init_colors():
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(C_HEADER, curses.COLOR_CYAN, -1)
    curses.init_pair(C_ACTIVE_TAB, curses.COLOR_BLACK, curses.COLOR_CYAN)
    curses.init_pair(C_INACTIVE_TAB, curses.COLOR_WHITE, -1)
    curses.init_pair(C_SELECTED, curses.COLOR_BLACK, curses.COLOR_GREEN)
    curses.init_pair(C_DIM, 8, -1)
    curses.init_pair(C_OK, curses.COLOR_GREEN, -1)
    curses.init_pair(C_WARN, curses.COLOR_YELLOW, -1)
    curses.init_pair(C_PROVIDER, curses.COLOR_MAGENTA, -1)
    curses.init_pair(C_SEARCH, curses.COLOR_CYAN, -1)
    curses.init_pair(C_STATUS, curses.COLOR_BLACK, curses.COLOR_WHITE)


TABS = ["Dashboard", "Providers", "Models", "Tiers", "Profiles", "Context"]


def _human(n: int) -> str:
    n = int(n)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M".replace(".0M", "M")
    if n >= 1000:
        return f"{round(n / 1000)}k"
    return str(n)


class App:
    def __init__(self, stdscr, cfg: dict):
        self.scr = stdscr
        self.cfg = cfg
        self.tab = 0
        self.cursor = 0
        self.scroll = 0
        self.search = ""
        self.searching = False
        self.models_cache: list[dict] = []
        self.status = ""
        self.tier_cursor = 0
        self.profile_cursor = 0
        self.prov_cursor = 0
        self.ctx_cursor = 0

    def _load_models(self, force: bool = False):
        self.models_cache = mdl.all_models(self.cfg, force=force)
        self.status = f"{len(self.models_cache)} models loaded"

    def _show_loading(self, msg: str = "Fetching models from providers..."):
        h, w = self.scr.getmaxyx()
        self.scr.erase()
        try:
            self.scr.addstr(
                h // 2, (w - len(msg)) // 2, msg,
                curses.color_pair(C_HEADER) | curses.A_BOLD,
            )
        except curses.error:
            pass
        self.scr.refresh()

    def run(self):
        _init_colors()
        curses.curs_set(0)
        integration.ensure_context_windows()
        self._show_loading()
        self._load_models(force=True)
        self.scr.timeout(100)
        while True:
            self._draw()
            k = self.scr.getch()
            if k == -1:
                continue
            if self.searching:
                if k == 27:
                    self.searching = False
                    self.search = ""
                elif k in (curses.KEY_BACKSPACE, 127, 8):
                    self.search = self.search[:-1]
                elif k == 10:
                    self.searching = False
                elif 32 <= k < 127:
                    self.search += chr(k)
                self.cursor = 0
                self.scroll = 0
                continue

            if k == ord("q"):
                break
            elif k == ord("\t") or k == curses.KEY_RIGHT:
                self.tab = (self.tab + 1) % len(TABS)
                self._reset_cursor()
            elif k == curses.KEY_BTAB or k == curses.KEY_LEFT:
                self.tab = (self.tab - 1) % len(TABS)
                self._reset_cursor()
            elif k == ord("/"):
                self.searching = True
                self.search = ""
            elif k == ord("r") or k == ord("R"):
                self._show_loading()
                self._load_models(force=True)
                self.status = f"{len(self.models_cache)} models refreshed"
            elif k == ord("L"):
                self._launch()
                return
            elif k == ord("u"):
                self._update()
            else:
                self._handle_tab_key(k)

    def _reset_cursor(self):
        self.cursor = 0
        self.scroll = 0

    def _handle_tab_key(self, k):
        if self.tab == 0:
            self._key_dashboard(k)
        elif self.tab == 1:
            self._key_providers(k)
        elif self.tab == 2:
            self._key_models(k)
        elif self.tab == 3:
            self._key_tiers(k)
        elif self.tab == 4:
            self._key_profiles(k)
        elif self.tab == 5:
            self._key_context(k)

    def _draw(self):
        self.scr.erase()
        h, w = self.scr.getmaxyx()
        self._draw_tabs(w)
        self._draw_help(h, w)

        if self.tab == 0:
            self._draw_dashboard(h, w)
        elif self.tab == 1:
            self._draw_providers(h, w)
        elif self.tab == 2:
            self._draw_models(h, w)
        elif self.tab == 3:
            self._draw_tiers(h, w)
        elif self.tab == 4:
            self._draw_profiles(h, w)
        elif self.tab == 5:
            self._draw_context(h, w)

        self._draw_status(h, w)
        self.scr.refresh()

    def _draw_tabs(self, w):
        x = 1
        for i, t in enumerate(TABS):
            label = f" {t} "
            pair = C_ACTIVE_TAB if i == self.tab else C_INACTIVE_TAB
            try:
                self.scr.addstr(0, x, label, curses.color_pair(pair))
            except curses.error:
                pass
            x += len(label) + 1
        try:
            self.scr.addstr(
                0, w - 16, " claude-hub ",
                curses.color_pair(C_HEADER) | curses.A_BOLD,
            )
        except curses.error:
            pass

    def _draw_help(self, h, w):
        helps = {
            0: "Tab:switch  L:launch  r:refresh  u:update  q:quit",
            1: "a:add  e:edit  d:delete  t:toggle  Enter:set key",
            2: "/:search  Enter:assign to tier  r:refresh",
            3: "Enter:change model  d:reset to default",
            4: "a:add  Enter:activate  d:delete  s:save current",
            5: "Enter:change  d:reset to default",
        }
        txt = helps.get(self.tab, "")
        try:
            self.scr.addstr(
                h - 1, 0, txt.center(w)[:w - 1],
                curses.color_pair(C_STATUS),
            )
        except curses.error:
            pass

    def _draw_status(self, h, w):
        if self.status:
            try:
                self.scr.addstr(h - 2, 2, self.status[:w - 4],
                                curses.color_pair(C_DIM))
            except curses.error:
                pass

    # ── Dashboard ─────────────────────────────────────────

    def _draw_dashboard(self, h, w):
        y = 2
        tiers = self.cfg.get("tiers", {})
        provs = self.cfg.get("providers", [])
        active_provs = [p for p in provs if p.get("active", True)]
        profile = self.cfg.get("active_profile", "default")

        self._title(y, "Current Configuration"); y += 2
        self._label(y, 4, "Profile:", profile); y += 1
        self._label(
            y, 4, "Provider:",
            active_provs[0]["name"] if active_provs else "none",
        )
        y += 1
        if active_provs:
            self._label(y, 4, "URL:", active_provs[0]["url"])
            y += 1
            key = config.get_key(active_provs[0])
            masked = key[:6] + "..." + key[-4:] if len(key) > 10 else key
            self._label(y, 4, "Key:", masked)
        y += 2

        ctx = config.context_settings(self.cfg)
        if ctx["disable_compact"]:
            self._label(y, 4, "Context:",
                        f"{_human(ctx['window'])} tokens, no compaction")
        else:
            self._label(y, 4, "Context:", "Claude Code default (200k, compacts)")
        y += 2

        self._title(y, "Tier Assignments"); y += 2
        for tier, label in config.TIER_LABELS.items():
            mid = tiers.get(tier, config.DEFAULT_TIERS[tier])
            name = self._model_name(mid)
            try:
                self.scr.addstr(y, 4, f"  {tier:<7}", curses.A_BOLD)
                self.scr.addstr(y, 14, name[:w - 16],
                                curses.color_pair(C_OK))
            except curses.error:
                pass
            y += 1

        y += 2
        self._title(y, "Statistics"); y += 2
        prov_count = len(provs)
        model_count = len(self.models_cache)
        providers_str = set(m["provider"] for m in self.models_cache)
        self._label(y, 4, "Providers:", str(prov_count)); y += 1
        self._label(y, 4, "Models:", str(model_count)); y += 1
        self._label(
            y, 4, "Sources:",
            ", ".join(sorted(providers_str)) if providers_str else "none",
        )

    def _key_dashboard(self, k):
        pass

    # ── Providers ─────────────────────────────────────────

    def _draw_providers(self, h, w):
        provs = self.cfg.get("providers", [])
        y = 2
        self._title(y, f"Providers ({len(provs)})"); y += 2

        for i, p in enumerate(provs):
            if y >= h - 3:
                break
            active = p.get("active", True)
            marker = "●" if active else "○"
            color = C_OK if active else C_DIM
            attr = curses.color_pair(C_SELECTED) if i == self.prov_cursor else 0
            key = config.get_key(p)
            has_key = "✓" if key else "✗"
            key_color = C_OK if key else C_WARN
            line = f"  {marker} {p['name']:<20} {p['type']:<10} {p['url']:<35}"
            try:
                self.scr.addstr(y, 2, line[:w - 4], attr)
                self.scr.addstr(
                    y, min(len(line) + 2, w - 8),
                    f" key:{has_key}",
                    curses.color_pair(key_color),
                )
            except curses.error:
                pass
            y += 1

    def _key_providers(self, k):
        provs = self.cfg.get("providers", [])
        if k in (curses.KEY_DOWN, ord("j")):
            if provs:
                self.prov_cursor = (self.prov_cursor + 1) % len(provs)
        elif k in (curses.KEY_UP, ord("k")):
            if provs:
                self.prov_cursor = (self.prov_cursor - 1) % len(provs)
        elif k == ord("t") and provs:
            p = provs[self.prov_cursor]
            p["active"] = not p.get("active", True)
            config.save(self.cfg)
            self._load_models()
        elif k == ord("a"):
            self._add_provider()
        elif k == ord("e") and provs:
            self._edit_provider(provs[self.prov_cursor])
        elif k == ord("d") and provs:
            provs.pop(self.prov_cursor)
            self.prov_cursor = max(0, self.prov_cursor - 1)
            config.save(self.cfg)
            self._load_models()
        elif k == 10 and provs:
            self._set_provider_key(provs[self.prov_cursor])

    def _add_provider(self):
        name = self._input_dialog("New Provider", "Name:")
        if not name:
            return
        ptype = self._choice_dialog(
            "Provider Type",
            ["gateway (CPA proxy)", "direct (API endpoint)"],
        )
        if ptype is None:
            return
        ptype_val = "gateway" if ptype == 0 else "direct"
        url = self._input_dialog(
            "Provider URL",
            "Base URL:",
            default="https://api.anthropic.com"
            if ptype_val == "direct" else "https://",
        )
        if not url:
            return
        key_file = self._input_dialog(
            "Key File",
            "Key file path (or empty for inline):",
            default=f"~/.secrets/key-{name.lower().replace(' ', '-')}",
        )

        provider = {
            "name": name,
            "type": ptype_val,
            "url": url,
            "key_file": key_file or "",
            "active": True,
        }

        key = self._input_dialog("API Key", "API Key (or empty to skip):")
        if key:
            config.set_key(provider, key)

        self.cfg.setdefault("providers", []).append(provider)
        config.save(self.cfg)
        self._load_models()
        self.status = f"Added provider: {name}"

    def _edit_provider(self, prov: dict):
        name = self._input_dialog("Edit Provider", "Name:", prov["name"])
        if name:
            prov["name"] = name
        url = self._input_dialog("Edit URL", "URL:", prov["url"])
        if url:
            prov["url"] = url
        config.save(self.cfg)
        self.status = f"Updated: {prov['name']}"

    def _set_provider_key(self, prov: dict):
        key = self._input_dialog(
            f"Set Key — {prov['name']}",
            "API Key:",
            mask=True,
        )
        if key:
            config.set_key(prov, key)
            config.save(self.cfg)
            self.status = f"Key saved for {prov['name']}"

    # ── Models ────────────────────────────────────────────

    def _filtered_models(self) -> list[dict]:
        if not self.search:
            return self.models_cache
        q = self.search.lower()
        return [
            m for m in self.models_cache
            if q in m["name"].lower() or q in m["provider"].lower()
            or q in m.get("clean_id", m["id"]).lower()
        ]

    def _draw_models(self, h, w):
        filtered = self._filtered_models()
        y = 2
        search_indicator = (
            f"  Search: {self.search}█"
            if self.searching
            else f"  /{self.search}" if self.search else ""
        )
        self._title(y, f"Models ({len(filtered)}/{len(self.models_cache)})")
        if search_indicator:
            try:
                self.scr.addstr(
                    y, 30, search_indicator[:w - 32],
                    curses.color_pair(C_SEARCH),
                )
            except curses.error:
                pass
        y += 2

        tiers = self.cfg.get("tiers", {})
        assigned_ids = set(tiers.values())
        visible = h - 6
        if self.cursor >= self.scroll + visible:
            self.scroll = self.cursor - visible + 1
        if self.cursor < self.scroll:
            self.scroll = self.cursor

        header = f"  {'Provider':<16} {'Model Name':<42} {'Tier':<8}"
        try:
            self.scr.addstr(y, 2, header[:w - 4],
                            curses.color_pair(C_DIM) | curses.A_UNDERLINE)
        except curses.error:
            pass
        y += 1

        for i in range(self.scroll, min(len(filtered), self.scroll + visible)):
            m = filtered[i]
            tier_mark = ""
            for t, mid in tiers.items():
                if mid == m["id"]:
                    tier_mark = t[:3]
                    break

            is_sel = i == self.cursor
            attr = curses.color_pair(C_SELECTED) if is_sel else 0
            prov_attr = (
                curses.color_pair(C_SELECTED)
                if is_sel
                else curses.color_pair(C_PROVIDER)
            )
            tier_attr = (
                curses.color_pair(C_SELECTED)
                if is_sel
                else curses.color_pair(C_WARN)
            )

            pointer = "▸ " if is_sel else "  "
            try:
                self.scr.addstr(y, 2, pointer, attr)
                self.scr.addstr(y, 4, f"{m['provider']:<16}", prov_attr)
                self.scr.addstr(y, 20, f"{m['name']:<42}"[:w - 30], attr)
                if tier_mark:
                    self.scr.addstr(y, min(62, w - 10), tier_mark, tier_attr)
            except curses.error:
                pass
            y += 1

    def _key_models(self, k):
        filtered = self._filtered_models()
        if k in (curses.KEY_DOWN, ord("j")):
            if filtered:
                self.cursor = min(self.cursor + 1, len(filtered) - 1)
        elif k in (curses.KEY_UP, ord("k")):
            self.cursor = max(self.cursor - 1, 0)
        elif k == curses.KEY_NPAGE:
            self.cursor = min(
                self.cursor + 10, len(filtered) - 1 if filtered else 0,
            )
        elif k == curses.KEY_PPAGE:
            self.cursor = max(self.cursor - 10, 0)
        elif k == 10 and filtered:
            m = filtered[self.cursor]
            tier = self._choice_dialog(
                f"Assign '{m['name']}' to tier",
                [f"{t} — {l}" for t, l in config.TIER_LABELS.items()],
            )
            if tier is not None:
                tier_key = list(config.TIER_LABELS.keys())[tier]
                self.cfg["tiers"][tier_key] = m["id"]
                config.save(self.cfg)
                self.status = f"{tier_key} → {m['name']}"

    # ── Tiers ─────────────────────────────────────────────

    def _draw_tiers(self, h, w):
        y = 2
        tiers = self.cfg.get("tiers", {})
        self._title(y, "Tier Configuration"); y += 2

        for i, (tier, label) in enumerate(config.TIER_LABELS.items()):
            mid = tiers.get(tier, config.DEFAULT_TIERS[tier])
            name = self._model_name(mid)
            is_sel = i == self.tier_cursor
            attr = curses.color_pair(C_SELECTED) if is_sel else 0
            pointer = "▸ " if is_sel else "  "
            is_default = mid == config.DEFAULT_TIERS.get(tier)

            try:
                self.scr.addstr(y, 2, pointer, attr)
                self.scr.addstr(y, 4, f"{tier:<7}", curses.A_BOLD | attr)
                self.scr.addstr(y, 12, label[:w - 14],
                                curses.color_pair(C_DIM))
                y += 1
                self.scr.addstr(y, 8, f"→ {name[:w - 12]}",
                                curses.color_pair(C_OK) | attr)
                if is_default:
                    self.scr.addstr(" (default)",
                                    curses.color_pair(C_DIM))
            except curses.error:
                pass
            y += 1
            try:
                self.scr.addstr(y, 8, f"  {mid[:w - 12]}",
                                curses.color_pair(C_DIM))
            except curses.error:
                pass
            y += 2

    def _key_tiers(self, k):
        tier_keys = list(config.TIER_LABELS.keys())
        if k in (curses.KEY_DOWN, ord("j")):
            self.tier_cursor = (self.tier_cursor + 1) % len(tier_keys)
        elif k in (curses.KEY_UP, ord("k")):
            self.tier_cursor = (self.tier_cursor - 1) % len(tier_keys)
        elif k == 10:
            tier = tier_keys[self.tier_cursor]
            models = self._filtered_models() or self.models_cache
            idx = self._model_picker(
                f"Select model for {tier}",
                models,
                self.cfg["tiers"].get(tier, ""),
            )
            if idx is not None:
                self.cfg["tiers"][tier] = models[idx]["id"]
                config.save(self.cfg)
                self.status = f"{tier} → {models[idx]['name']}"
        elif k == ord("d"):
            tier = tier_keys[self.tier_cursor]
            self.cfg["tiers"][tier] = config.DEFAULT_TIERS[tier]
            config.save(self.cfg)
            self.status = f"{tier} reset to default"

    # ── Profiles ──────────────────────────────────────────

    def _draw_profiles(self, h, w):
        y = 2
        profiles = self.cfg.get("profiles", {})
        active = self.cfg.get("active_profile", "default")
        self._title(y, f"Profiles ({len(profiles)})"); y += 2

        for i, (name, tiers) in enumerate(profiles.items()):
            is_sel = i == self.profile_cursor
            is_active = name == active
            attr = curses.color_pair(C_SELECTED) if is_sel else 0
            marker = "● " if is_active else "○ "
            pointer = "▸ " if is_sel else "  "

            try:
                self.scr.addstr(y, 2, pointer, attr)
                self.scr.addstr(y, 4, marker,
                                curses.color_pair(C_OK) if is_active
                                else curses.color_pair(C_DIM))
                self.scr.addstr(f"{name}", curses.A_BOLD | attr)
            except curses.error:
                pass
            y += 1

            for tier in ("FABLE", "OPUS", "SONNET", "HAIKU"):
                mid = tiers.get(tier, "?")
                name_disp = self._model_name(mid)
                try:
                    self.scr.addstr(y, 8, f"{tier:<7} ",
                                    curses.color_pair(C_DIM))
                    self.scr.addstr(name_disp[:w - 20],
                                    curses.color_pair(C_OK) if is_active
                                    else 0)
                except curses.error:
                    pass
                y += 1
            y += 1

    def _key_profiles(self, k):
        profiles = self.cfg.get("profiles", {})
        pnames = list(profiles.keys())
        if k in (curses.KEY_DOWN, ord("j")):
            if pnames:
                self.profile_cursor = (
                    (self.profile_cursor + 1) % len(pnames)
                )
        elif k in (curses.KEY_UP, ord("k")):
            if pnames:
                self.profile_cursor = (
                    (self.profile_cursor - 1) % len(pnames)
                )
        elif k == 10 and pnames:
            name = pnames[self.profile_cursor]
            self.cfg["active_profile"] = name
            self.cfg["tiers"] = dict(profiles[name])
            config.save(self.cfg)
            self.status = f"Activated profile: {name}"
        elif k == ord("a"):
            name = self._input_dialog("New Profile", "Profile name:")
            if name:
                self.cfg.setdefault("profiles", {})[name] = dict(
                    self.cfg.get("tiers", config.DEFAULT_TIERS)
                )
                config.save(self.cfg)
                self.status = f"Created profile: {name}"
        elif k == ord("s"):
            active = self.cfg.get("active_profile", "default")
            self.cfg.setdefault("profiles", {})[active] = dict(
                self.cfg.get("tiers", {})
            )
            config.save(self.cfg)
            self.status = f"Saved current tiers to profile: {active}"
        elif k == ord("d") and pnames:
            name = pnames[self.profile_cursor]
            if name == "default":
                self.status = "Cannot delete default profile"
            else:
                del profiles[name]
                self.profile_cursor = max(0, self.profile_cursor - 1)
                config.save(self.cfg)
                self.status = f"Deleted profile: {name}"

    # ── Context ───────────────────────────────────────────

    CTX_ROWS = ("window", "disable_compact", "statusline")

    def _draw_context(self, h, w):
        ctx = config.context_settings(self.cfg)
        state = integration.statusline_state()
        y = 2

        if ctx["disable_compact"]:
            window = f"{_human(ctx['window'])} tokens"
            compaction = "off, the window above is in force"
        else:
            window = f"{_human(ctx['window'])} tokens (not applied)"
            compaction = "on, Claude Code compacts at its own 200k floor"

        statusline = {
            "ours": "on, registered in ~/.claude/settings.json",
            "none": "on, registers itself at launch",
            "other": "on, but another statusline is configured",
        }[state] if ctx["statusline"] else "off"

        rows = [
            ("Window", window, ctx["disable_compact"]),
            ("Compaction", compaction, not ctx["disable_compact"]),
            ("Statusline", statusline, ctx["statusline"] and state != "other"),
        ]

        self._title(y, "Context Window"); y += 2
        for i, (name, value, good) in enumerate(rows):
            is_sel = i == self.ctx_cursor
            attr = curses.color_pair(C_SELECTED) if is_sel else 0
            pointer = "▸ " if is_sel else "  "
            colour = curses.color_pair(C_OK if good else C_WARN)
            try:
                self.scr.addstr(y, 2, pointer, attr)
                self.scr.addstr(y, 4, f"{name:<12}", curses.A_BOLD | attr)
                self.scr.addstr(y, 17, value[:w - 19], colour)
            except curses.error:
                pass
            y += 1

        y += 1
        for line in (
            "Claude Code trusts a model's real window only on the first-party",
            "API. Behind a gateway it assumes 200k and compacts there. Raising",
            "the window is the same switch as turning compaction off: /compact",
            "stops working too, and past the model's real limit the API starts",
            "refusing requests, so the way out becomes /clear.",
            "",
            "The statusline draws against the real windows below, not against",
            "the number above, and turns red before the real limit.",
        ):
            try:
                self.scr.addstr(y, 4, line[:w - 6], curses.color_pair(C_DIM))
            except curses.error:
                pass
            y += 1

        y += 1
        windows = integration.context_windows()
        self._title(y, f"Real Windows ({len(windows)})"); y += 2
        for key, value in sorted(windows.items()):
            if y >= h - 3:
                break
            try:
                self.scr.addstr(y, 4, f"{key[:28]:<30}",
                                curses.color_pair(C_PROVIDER))
                self.scr.addstr(_human(value), curses.color_pair(C_DIM))
            except curses.error:
                pass
            y += 1
        if y < h - 3:
            try:
                self.scr.addstr(y, 4, f"edit: {integration.CTX_WINDOWS_FILE}",
                                curses.color_pair(C_DIM))
            except curses.error:
                pass

    def _key_context(self, k):
        ctx = config.context_settings(self.cfg)
        row = self.CTX_ROWS[self.ctx_cursor]

        if k in (curses.KEY_DOWN, ord("j")):
            self.ctx_cursor = (self.ctx_cursor + 1) % len(self.CTX_ROWS)
            return
        if k in (curses.KEY_UP, ord("k")):
            self.ctx_cursor = (self.ctx_cursor - 1) % len(self.CTX_ROWS)
            return

        if k == ord("d"):
            ctx[row] = config.DEFAULT_CONTEXT[row]
            self.status = f"{row} reset to default"
        elif k == 10:
            if row == "window":
                value = self._input_dialog(
                    "Context window", "tokens:", str(ctx["window"]),
                )
                if value is None:
                    return
                try:
                    ctx["window"] = max(1, int(value.strip().replace("_", "")))
                except ValueError:
                    self.status = "Not a number"
                    return
                self.status = f"Window: {_human(ctx['window'])} (applies next launch)"
            else:
                ctx[row] = not ctx[row]
                self.status = f"{row}: {'on' if ctx[row] else 'off'}"
        else:
            return

        self.cfg["context"] = ctx
        config.save(self.cfg)
        integration.ensure_context_windows()

        # The statusline is registered in Claude Code's own settings, so the
        # toggle has to reach across into them right now.
        if ctx["statusline"]:
            integration.install_statusline()
        else:
            integration.remove_statusline()

    # ── Dialogs ───────────────────────────────────────────

    def _input_dialog(
        self, title: str, prompt: str,
        default: str = "", mask: bool = False,
    ) -> str | None:
        h, w = self.scr.getmaxyx()
        dw = min(60, w - 4)
        dh = 5
        dy = h // 2 - 2
        dx = (w - dw) // 2
        win = curses.newwin(dh, dw, dy, dx)
        win.attron(curses.color_pair(C_HEADER))
        win.border()
        win.attroff(curses.color_pair(C_HEADER))
        win.addstr(0, 2, f" {title} ", curses.color_pair(C_HEADER))

        value = default
        curses.curs_set(1)
        while True:
            win.move(2, 2)
            win.clrtoeol()
            win.addstr(2, 2, f"{prompt} ", curses.color_pair(C_DIM))
            display = "*" * len(value) if mask else value
            visible = display[-(dw - len(prompt) - 6):]
            win.addstr(visible)
            win.border()
            win.addstr(0, 2, f" {title} ", curses.color_pair(C_HEADER))
            win.refresh()
            k = win.getch()
            if k == 27:
                curses.curs_set(0)
                return None
            elif k in (10, 13):
                curses.curs_set(0)
                return value
            elif k in (curses.KEY_BACKSPACE, 127, 8):
                value = value[:-1]
            elif 32 <= k < 127:
                value += chr(k)
        curses.curs_set(0)
        return None

    def _choice_dialog(
        self, title: str, options: list[str],
    ) -> int | None:
        h, w = self.scr.getmaxyx()
        dw = min(60, w - 4)
        dh = len(options) + 4
        dy = h // 2 - dh // 2
        dx = (w - dw) // 2
        win = curses.newwin(dh, dw, dy, dx)
        sel = 0

        while True:
            win.erase()
            win.attron(curses.color_pair(C_HEADER))
            win.border()
            win.attroff(curses.color_pair(C_HEADER))
            win.addstr(0, 2, f" {title} ", curses.color_pair(C_HEADER))
            for i, opt in enumerate(options):
                attr = (
                    curses.color_pair(C_SELECTED) if i == sel
                    else curses.color_pair(C_DIM)
                )
                pointer = "▸ " if i == sel else "  "
                try:
                    win.addstr(i + 2, 2, f"{pointer}{opt}"[:dw - 4], attr)
                except curses.error:
                    pass
            win.refresh()
            k = win.getch()
            if k == 27:
                return None
            elif k in (curses.KEY_DOWN, ord("j")):
                sel = (sel + 1) % len(options)
            elif k in (curses.KEY_UP, ord("k")):
                sel = (sel - 1) % len(options)
            elif k in (10, 13):
                return sel

    def _model_picker(
        self, title: str, models: list[dict], current_id: str,
    ) -> int | None:
        h, w = self.scr.getmaxyx()
        sel = 0
        for i, m in enumerate(models):
            if m["id"] == current_id:
                sel = i
                break
        scroll = max(0, sel - 5)
        query = ""

        while True:
            filtered = [
                (i, m) for i, m in enumerate(models)
                if query.lower() in m["name"].lower()
                or query.lower() in m["provider"].lower()
            ] if query else list(enumerate(models))

            if not filtered:
                filtered = [(0, {"name": "no matches", "provider": "",
                                 "id": ""})]
            sel = max(0, min(sel, len(filtered) - 1))
            visible = h - 8
            if sel >= scroll + visible:
                scroll = sel - visible + 1
            if sel < scroll:
                scroll = sel

            self.scr.erase()
            self._title(1, title)
            search_line = f"  Search: {query}█" if query else "  Type to search"
            try:
                self.scr.addstr(2, 2, search_line[:w - 4],
                                curses.color_pair(C_SEARCH))
            except curses.error:
                pass

            y = 4
            for vi in range(
                scroll, min(len(filtered), scroll + visible)
            ):
                orig_i, m = filtered[vi]
                is_sel = vi == sel
                is_cur = m["id"] == current_id
                attr = curses.color_pair(C_SELECTED) if is_sel else 0
                marker = " ●" if is_cur else "  "
                pointer = "▸" if is_sel else " "
                try:
                    self.scr.addstr(y, 1, pointer, attr)
                    self.scr.addstr(
                        y, 2,
                        f"{marker} {m['provider']:<14} {m['name']}"[:w - 4],
                        attr,
                    )
                except curses.error:
                    pass
                y += 1

            try:
                self.scr.addstr(
                    h - 2, 2,
                    "↑↓:navigate  Enter:select  Esc:cancel  type:search",
                    curses.color_pair(C_DIM),
                )
            except curses.error:
                pass
            self.scr.refresh()

            k = self.scr.getch()
            if k == 27:
                return None
            elif k in (curses.KEY_DOWN, ord("j")):
                sel = min(sel + 1, len(filtered) - 1)
            elif k in (curses.KEY_UP, ord("k")):
                sel = max(sel - 1, 0)
            elif k == curses.KEY_NPAGE:
                sel = min(sel + 10, len(filtered) - 1)
            elif k == curses.KEY_PPAGE:
                sel = max(sel - 10, 0)
            elif k in (10, 13):
                if filtered and filtered[sel][1]["id"]:
                    return filtered[sel][0]
            elif k in (curses.KEY_BACKSPACE, 127, 8):
                query = query[:-1]
                sel = 0
                scroll = 0
            elif 32 <= k < 127:
                query += chr(k)
                sel = 0
                scroll = 0

    # ── Helpers ───────────────────────────────────────────

    def _model_name(self, model_id: str) -> str:
        for m in self.models_cache:
            if m["id"] == model_id or m.get("clean_id") == model_id:
                return m["name"]
        return model_id

    def _title(self, y: int, text: str):
        try:
            self.scr.addstr(
                y, 2, f"── {text} ",
                curses.color_pair(C_HEADER) | curses.A_BOLD,
            )
        except curses.error:
            pass

    def _label(self, y: int, x: int, label: str, value: str):
        try:
            self.scr.addstr(y, x, label, curses.color_pair(C_DIM))
            self.scr.addstr(f" {value}", curses.A_BOLD)
        except curses.error:
            pass

    def _launch(self):
        curses.endwin()
        launch(self.cfg)

    def _update(self):
        self._show_loading("Checking for updates...")
        pending, note = updater.check()
        if not pending:
            self.status = f"Update: {note}"
            return

        dirty = updater.local_changes()
        options = [f"Update now ({note})", "Cancel"]
        if dirty:
            options.insert(1, f"Discard {len(dirty)} local change(s) and update")
        choice = self._choice_dialog("claude-hub update", options)
        if choice is None or options[choice] == "Cancel":
            self.status = "Update cancelled"
            return

        self._show_loading("Updating...")
        ok, note = updater.update(force=choice == 1 and bool(dirty))
        if not ok:
            self.status = f"Update failed: {note}"
            return

        ctx = config.context_settings(self.cfg)
        integration.install(statusline=ctx.get("statusline", True))
        self.status = f"Updated {note}. Restart claude-hub to load it."


def run_tui(cfg: dict):
    os.environ.setdefault("ESCDELAY", "25")
    curses.wrapper(lambda scr: App(scr, cfg).run())
