"""Streamlit UI for browsing sessions and the vault.

Generation still happens inside your coding agent via the MCP server -- this
UI is the read+manage surface: see what's saved, view drafts, mark posted.
"""

from __future__ import annotations

import streamlit as st

from ship_and_tell import sources, vault

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
    days = st.sidebar.slider("Days back", 1, 30, 7)
    project_filter = st.sidebar.text_input(
        "Project contains", "", help="Case-insensitive substring of the cwd"
    )
    min_turns = st.sidebar.number_input("Min user turns", min_value=0, value=0, step=1)

    return {
        "agent_key": agent_key,
        "days": days,
        "project_filter": project_filter or None,
        "min_turns": int(min_turns),
    }


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

    st.caption(
        f"{len(sessions)} sessions in last {filters['days']}d"
        + (f" with ≥{filters['min_turns']} turns" if filters["min_turns"] else "")
        + (f" matching '{filters['project_filter']}'" if filters["project_filter"] else "")
    )

    if not sessions:
        st.info("No sessions match these filters.")
        return

    for s in sessions:
        d = s.to_dict()
        title = f"**{d['project']}** — {d['user_turn_count']} turns — {d['last_active_at'][:10]}"
        with st.expander(title):
            cols = st.columns(4)
            cols[0].metric("User turns", d["user_turn_count"])
            cols[1].metric("Total records", d["message_count"])
            cols[2].write(f"**Branch**\n\n`{d.get('git_branch') or '—'}`")
            cols[3].write(f"**Model**\n\n`{d.get('model') or '—'}`")
            st.write(f"**Session ID:** `{d['session_id']}`")
            if d["first_user_message"]:
                st.markdown(f"**First message:** {d['first_user_message']}")

            if st.button("Show summary", key=f"show_{d['session_id']}"):
                with st.spinner("Reading…"):
                    out = adapter.read_session(
                        d["session_id"], format="summary", max_turns=60
                    )
                st.caption(
                    f"{out['returned_turn_count']} / {out['turn_count']} turns shown"
                    + (" (truncated)" if out.get("truncated") else "")
                )
                for t in out["turns"]:
                    role = t["role"]
                    text = t["text"]
                    if role == "user":
                        st.markdown(f"**🧑 user** — {text[:1200]}")
                    elif role == "assistant":
                        st.markdown(f"**🤖 assistant** — {text[:1200]}")
                    else:
                        st.caption(text)


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
