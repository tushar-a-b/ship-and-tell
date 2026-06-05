"""Streamlit UI for browsing sessions and the vault.

Generation still happens inside your coding agent via the MCP server -- this
UI is the read+manage surface: see what's saved, view drafts, mark posted.
"""

from __future__ import annotations

import streamlit as st

from ship_and_tell import claude_code, sources, vault

st.set_page_config(page_title="Ship & Tell", page_icon="🚢", layout="wide")


def _agent_label(key: str, cfg: dict) -> str:
    if cfg["status"] == "ready":
        return cfg["name"]
    return f"{cfg['name']} (coming soon)"


def _sidebar() -> dict:
    st.sidebar.title("🚢 Ship & Tell")
    st.sidebar.caption("Browse sessions, manage saved insights.")

    agent_keys = list(sources.AVAILABLE.keys())
    ready_keys = [k for k in agent_keys if sources.AVAILABLE[k]["status"] == "ready"]
    default_idx = agent_keys.index(ready_keys[0]) if ready_keys else 0
    agent_key = st.sidebar.selectbox(
        "Source",
        agent_keys,
        index=default_idx,
        format_func=lambda k: _agent_label(k, sources.AVAILABLE[k]),
    )

    if sources.AVAILABLE[agent_key]["status"] != "ready":
        st.sidebar.warning(
            f"{sources.AVAILABLE[agent_key]['name']} adapter is planned but not yet implemented. "
            "Switch to a ready source above."
        )

    st.sidebar.divider()
    st.sidebar.subheader("Session filters")

    DAY_PRESETS: list[tuple[str, int | None]] = [
        ("Last 24 hours", 1),
        ("Last 3 days", 3),
        ("Last 7 days", 7),
        ("Last 14 days", 14),
        ("Last 30 days", 30),
        ("Last 60 days", 60),
        ("Last 90 days", 90),
        ("Last 180 days", 180),
        ("Last year", 365),
        ("Last 2 years", 730),
        ("Custom…", None),
    ]
    preset_labels = [p[0] for p in DAY_PRESETS]
    preset_idx = st.sidebar.selectbox(
        "Time range",
        list(range(len(DAY_PRESETS))),
        index=2,
        format_func=lambda i: preset_labels[i],
    )
    selected_days = DAY_PRESETS[preset_idx][1]
    if selected_days is None:
        selected_days = st.sidebar.number_input(
            "Custom days back",
            min_value=1,
            max_value=3650,
            value=14,
            step=1,
        )

    project_filter = st.sidebar.text_input(
        "Project contains", "", help="Case-insensitive substring of the cwd"
    )
    min_turns = st.sidebar.number_input("Min user turns", min_value=0, value=0, step=1)

    st.sidebar.divider()
    st.sidebar.subheader("Summary view")
    st.sidebar.caption(
        "When you click *Show summary* on a session, this is how many user+assistant "
        "turns to load. Tool calls, tool results, thinking blocks, and system meta are "
        "always stripped. Longer sessions keep the head + tail and elide the middle."
    )
    max_turns = st.sidebar.number_input(
        "Max turns shown", min_value=20, max_value=2000, value=60, step=20
    )

    return {
        "agent_key": agent_key,
        "days": int(selected_days),
        "project_filter": project_filter or None,
        "min_turns": int(min_turns),
        "max_turns": int(max_turns),
    }


def _render_turns(turns: list[dict]) -> None:
    """Render a list of turn dicts produced by claude_code.read_session.

    Handles all roles: user, assistant, agent_task (synthetic subagent brief),
    subagent_marker (boundary indicator inside the parent), and system
    (elision notice).
    """
    for t in turns:
        role = t.get("role")
        text = t.get("text", "")
        if role == "user":
            st.markdown(f"**🧑 user**\n\n{text}")
        elif role == "assistant":
            st.markdown(f"**🤖 assistant**\n\n{text}")
        elif role == "agent_task":
            st.markdown(f"**📋 agent_task** *(synthetic — task brief from parent)*\n\n{text}")
        elif role == "subagent_marker":
            st.info(text, icon="🧠")
        else:
            st.caption(text)
        st.divider()


def _sessions_tab(filters: dict) -> None:
    agent_key = filters["agent_key"]
    cfg = sources.AVAILABLE[agent_key]
    if cfg["status"] != "ready":
        st.info(
            f"{cfg['name']} sessions are not browsable yet. "
            f"Transcripts will be read from `{cfg['transcripts_at']}` once the adapter ships."
        )
        return

    adapter = sources.get_adapter(agent_key)
    sessions = adapter.list_recent(
        days=filters["days"],
        min_user_turns=filters["min_turns"],
        project_filter=filters["project_filter"],
    )

    days = filters["days"]
    if days >= 365:
        range_label = f"{days // 365} year{'s' if days // 365 > 1 else ''}"
        rem = days % 365
        if rem:
            range_label += f" {rem}d"
    elif days >= 30:
        range_label = f"{days // 30} month{'s' if days // 30 > 1 else ''}"
        rem = days % 30
        if rem:
            range_label += f" {rem}d"
    else:
        range_label = f"{days}d"
    st.caption(
        f"{len(sessions)} sessions in last {range_label}"
        + (f" with ≥{filters['min_turns']} turns" if filters["min_turns"] else "")
        + (f" matching '{filters['project_filter']}'" if filters["project_filter"] else "")
    )

    if not sessions:
        st.info("No sessions match these filters.")
        return

    for s in sessions:
        d = s.to_dict()
        sub_n = d.get("subagent_count") or 0
        badge = f" · 🧠 {sub_n} subagents" if sub_n else ""
        title = (
            f"**{d['project']}** — {d['user_turn_count']} turns "
            f"— {d['last_active_at'][:10]}{badge}"
        )
        with st.expander(title):
            cols = st.columns(5)
            cols[0].metric("User turns", d["user_turn_count"])
            cols[1].metric("Total records", d["message_count"])
            cols[2].metric("Subagents", sub_n)
            cols[3].write(f"**Branch**\n\n`{d.get('git_branch') or '—'}`")
            cols[4].write(f"**Model**\n\n`{d.get('model') or '—'}`")
            st.write(f"**Session ID:** `{d['session_id']}`")
            if d["first_user_message"]:
                st.markdown(f"**First message:** {d['first_user_message']}")

            include_subs = False
            if sub_n:
                include_subs = st.checkbox(
                    f"Include {sub_n} subagent transcript(s) in summary "
                    f"(parent tool_result dropped to avoid double-counting)",
                    key=f"inc_{d['session_id']}",
                )

            if st.button("Show summary", key=f"show_{d['session_id']}"):
                with st.spinner("Reading…"):
                    out = adapter.read_session(
                        d["session_id"],
                        format="summary",
                        max_turns=filters["max_turns"],
                        include_subagents=("summary" if include_subs else "none"),
                        max_subagent_turns=40,
                    )
                tail = " · tool calls, tool results, thinking, and meta wrappers stripped"
                if include_subs:
                    tail += (
                        f" · subagent markers inserted; "
                        f"{out.get('subagent_count', 0)} subagent section(s) appended; "
                        f"{out.get('unmatched_subagent_count', 0)} orphans"
                    )
                st.caption(
                    f"{out['returned_turn_count']} of {out['turn_count']} turns shown"
                    + (" — middle elided" if out.get("truncated") else "")
                    + tail
                )
                _render_turns(out["turns"])

                if include_subs and out.get("subagent_sections"):
                    for sec in out["subagent_sections"]:
                        flag = "matched" if sec.get("matched_to_parent") else "orphan"
                        st.markdown(
                            f"### 🧠 Subagent — {sec.get('agent_type') or 'unknown'} "
                            f"({flag})\n"
                            f"*{sec.get('description') or '(no description)'}*"
                        )
                        st.caption(
                            f"{sec['returned_turn_count']} of {sec['turn_count']} subagent turns"
                            + (" — middle elided" if sec.get("truncated") else "")
                        )
                        _render_turns(sec["turns"])

            if sub_n and st.button(
                f"List {sub_n} subagent(s)",
                key=f"list_sub_{d['session_id']}",
            ):
                with st.spinner("Loading subagent index…"):
                    subs_meta = claude_code.list_subagents(d["session_id"])
                for sub in subs_meta:
                    sm = sub.to_dict()
                    desc = sm["description"] or "(no description)"
                    atype = sm["agent_type"] or "unknown"
                    with st.container():
                        st.markdown(
                            f"**🧠 {atype}** — *{desc}*  \n"
                            f"`{sm['agent_id']}` · {sm['message_count']} records · model `{sm.get('model') or '—'}`"
                        )
                        if st.button(
                            "Show subagent summary",
                            key=f"show_sub_{d['session_id']}_{sm['agent_id']}",
                        ):
                            with st.spinner("Reading subagent…"):
                                sout = claude_code.read_subagent(
                                    d["session_id"], sm["agent_id"], max_turns=80
                                )
                            st.caption(
                                f"{sout['returned_turn_count']} of {sout['turn_count']} turns"
                                + (" — middle elided" if sout.get("truncated") else "")
                            )
                            _render_turns(sout["turns"])
                        st.divider()


def _vault_tab() -> None:
    col_a, col_b, col_c = st.columns([2, 2, 6])
    status = col_a.radio(
        "Show", ["All", "Unposted", "Posted"], horizontal=True, label_visibility="collapsed"
    )
    limit = col_b.number_input("Limit", min_value=10, max_value=1000, value=100, step=10)

    posted_filter = None
    if status == "Unposted":
        posted_filter = False
    elif status == "Posted":
        posted_filter = True

    entries = vault.list_vault(limit=int(limit), posted=posted_filter)
    col_c.caption(
        f"Vault at `{vault.VAULT_PATH}` — showing {len(entries)} entries"
    )

    if not entries:
        st.info(
            "Nothing yet. Run a digest inside Claude Code "
            "(*'run the ship-and-tell weekly digest'*) to populate the vault."
        )
        return

    for e in entries:
        badge = "✅ posted" if e.get("posted") else "⬜ unposted"
        title = e.get("title") or "(untitled)"
        project = e.get("project") or ""
        header = f"{badge} — {title}"
        if project:
            header += f" — `{project}`"
        with st.expander(header):
            st.caption(f"id: `{e['id']}`  ·  created: {e.get('created_at', '')}")

            if e.get("lesson"):
                st.markdown(f"**Lesson**  \n{e['lesson']}")
            if e.get("problem"):
                st.markdown(f"**Problem**  \n{e['problem']}")
            if e.get("root_cause"):
                st.markdown(f"**Root cause**  \n{e['root_cause']}")

            links = e.get("links") or []
            if links:
                badges = []
                for ln in links:
                    if not isinstance(ln, dict):
                        continue
                    ltype = (ln.get("type") or "link").lower()
                    url = ln.get("url") or ""
                    label = ln.get("label") or url
                    icon = {
                        "pr": "🔀",
                        "commit": "🧱",
                        "release": "🚀",
                        "issue": "🐛",
                        "session": "💬",
                    }.get(ltype, "🔗")
                    if url.startswith(("http://", "https://")):
                        badges.append(f"{icon} [{label}]({url})")
                    else:
                        badges.append(f"{icon} {label}")
                if badges:
                    st.markdown("**Links**  \n" + "  \n".join(badges))

            content_tabs = st.tabs(["Tweet", "Thread", "Article", "JSON"])
            with content_tabs[0]:
                if e.get("tweet"):
                    st.text_area(
                        "tweet",
                        value=e["tweet"],
                        height=120,
                        key=f"tw_{e['id']}",
                        label_visibility="collapsed",
                    )
                    st.caption(f"{len(e['tweet'])} chars")
                else:
                    st.caption("No tweet draft.")
            with content_tabs[1]:
                if e.get("thread"):
                    st.text_area(
                        "thread",
                        value=e["thread"],
                        height=240,
                        key=f"th_{e['id']}",
                        label_visibility="collapsed",
                    )
                else:
                    st.caption("No thread draft.")
            with content_tabs[2]:
                if e.get("article"):
                    st.text_area(
                        "article",
                        value=e["article"],
                        height=240,
                        key=f"ar_{e['id']}",
                        label_visibility="collapsed",
                    )
                else:
                    st.caption("No article draft.")
            with content_tabs[3]:
                st.json(e)

            tags = e.get("tags") or []
            if tags:
                st.markdown(" ".join(f"`#{t}`" for t in tags))

            b1, b2, _ = st.columns([1, 1, 4])
            if e.get("posted"):
                if b1.button("Mark unposted", key=f"unpost_{e['id']}"):
                    vault.mark_posted(e["id"], posted=False)
                    st.rerun()
            else:
                if b1.button("Mark posted", key=f"post_{e['id']}"):
                    vault.mark_posted(e["id"], posted=True)
                    st.rerun()
            if e.get("source_session_id"):
                b2.caption(f"src: `{e['source_session_id'][:8]}…`")


def main() -> None:
    filters = _sidebar()
    tab_vault, tab_sessions = st.tabs(["📦 Vault", "💬 Sessions"])
    with tab_vault:
        _vault_tab()
    with tab_sessions:
        _sessions_tab(filters)


main()
