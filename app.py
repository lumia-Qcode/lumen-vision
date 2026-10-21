"""Lumen Vision: Streamlit console for search, alert verification, evaluation and a live gate check."""
import json
import tempfile
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from lumen import alerts, db, evaluate, ui
from lumen.config import GATE_THRESHOLDS, INDEX_DIR, ROOT
from lumen.search import Index, search

st.set_page_config(page_title="Lumen Vision", page_icon=":material/videocam:", layout="wide")
st.markdown(ui.CSS, unsafe_allow_html=True)


@st.cache_resource(show_spinner="Loading search models")
def resources():
    con = db.connect()
    return con, Index(con)


con, index = resources()


def when(ts):
    return datetime.fromisoformat(ts).strftime("%d %b %Y, %H:%M")


def clip_card(c):
    st.video(str(ROOT / c["path"]))
    st.markdown(ui.meta(c["camera_id"], c.get("site_name", ""), when(c["recorded_at"])), unsafe_allow_html=True)
    hz = db.rows(con, "SELECT type, final_conf FROM hazards WHERE clip_id = ? ORDER BY final_conf DESC", (c["id"],))
    st.markdown(ui.chips(hz, c.get("tags")), unsafe_allow_html=True)
    for ic in db.rows(con, "SELECT * FROM interpretations WHERE clip_id = ?", (c["id"],)):
        st.markdown(ui.judgement(ic["claim"], ic["rationale"]), unsafe_allow_html=True)
    with st.expander("What the system saw"):
        v = db.rows(con, "SELECT raw_json, model FROM vlm_outputs WHERE clip_id = ?", (c["id"],))
        if v:
            st.caption(f"Structured observations from {v[0]['model']}")
            st.json(json.loads(v[0]["raw_json"]), expanded=False)
        else:
            st.caption("Not sent to the VLM. Described by the gate only.")
            st.write(c.get("tags", ""))
        st.caption("Gate scores")
        st.json(json.loads(c["gate_json"])["scores"], expanded=False)


report_path = INDEX_DIR / "eval_report.json"
report = json.loads(report_path.read_text()) if report_path.exists() else None
pending_n = db.rows(con, "SELECT COUNT(*) n FROM alerts WHERE status = 'pending'")[0]["n"]
clips_n = db.rows(con, "SELECT COUNT(*) n FROM clips")[0]["n"]
frame_pct = report["cost"]["frames_pct_to_vlm"] if report else "–"
st.markdown(ui.hero(clips_n, pending_n, frame_pct), unsafe_allow_html=True)

tab_search, tab_room, tab_alerts, tab_eval, tab_live = st.tabs(
    ["Search", "Room watch", "Alerts", "Evaluation", "Live check"])

# ---------------------------------------------------------------- multi-camera room agents
with tab_room:
    from lumen.agents import RoomCoordinator, load_rooms
    from lumen import room_ui

    rooms = load_rooms()
    st.markdown('<p class="lv-note">Each camera in a room runs as its own agent. Ask the room a question: the '
                'coordinator broadcasts it, every camera searches its own angle, quiet cameras are asked to verify, '
                'and cameras hand the subject to each other as it moves between their views. The demo rooms use '
                'the three lenses of a multi-sensor unit cut from one real camera, so all angles share a clock.</p>',
                unsafe_allow_html=True)
    c1, c2 = st.columns([1, 2], gap="medium")
    room_id = c1.selectbox("Room", list(rooms), format_func=lambda r: rooms[r]["name"])
    room_examples = {"tower-a-compound": ["people near the cabinets at night", "person crouching on the gravel",
                                          "someone walking along the fence"],
                     "hub-b-shelter": ["technician working inside the shelter cabinet", "man in a pink shirt near the tower",
                                       "people at the tower base"]}
    rq = c2.selectbox("Ask the room", room_examples.get(room_id, []) + ["Write my own question"])
    if rq == "Write my own question":
        rq = st.text_input("Your question", placeholder="e.g. person carrying something out of the shelter")
    if rq and st.button("Ask the cameras", type="primary"):
        with st.spinner("Cameras are talking"):
            st.session_state.room_result = RoomCoordinator(room_id, con).ask(rq)
    res = st.session_state.get("room_result")
    if res and res["room"] == room_id:
        st.components.v1.html(room_ui.render(res), height=1090, scrolling=False)

# ---------------------------------------------------------------- search
with tab_search:
    examples = ["person at the tower site at night", "smoke rising into the sky",
                "camera 4371 person at the equipment cabinet", "workers wearing hard hats", "fire at the hub after 6pm"]
    def use_example():
        if st.session_state.example:
            st.session_state.q = st.session_state.example

    st.pills("Examples", examples, label_visibility="collapsed", key="example", on_change=use_example)
    q = st.text_input("Search footage", key="q", label_visibility="collapsed",
                      placeholder="Describe what you're looking for, e.g. person near the cabinets at night")
    if q:
        parsed, results = search(index, q, k=9)
        st.markdown(ui.parse_box(parsed["filters"], parsed["residue"], parsed["hazards"]), unsafe_allow_html=True)
        if not results:
            st.info("No clips match those filters. Remove a time, camera or site word and search again.")
        cols = st.columns(3, gap="medium")
        for i, r in enumerate(results):
            with cols[i % 3]:
                with st.container(border=True):
                    st.markdown(f'<div class="lv-rank"><b>Match {i + 1}</b><span>score {r["score"]:.3f}</span></div>',
                                unsafe_allow_html=True)
                    clip_card(r)
    else:
        st.markdown('<p class="lv-note">Search in plain language. Camera, site and time words become exact filters; '
                    'the rest is matched against what the clips look like and what the models described.</p>',
                    unsafe_allow_html=True)

# ---------------------------------------------------------------- alerts
with tab_alerts:
    status = st.segmented_control("Status", ["pending", "confirmed", "rejected"], default="pending",
                                  format_func=str.capitalize, label_visibility="collapsed") or "pending"
    rows = db.rows(con, """SELECT a.*, c.path, c.camera_id, c.recorded_at, c.gate_json, c.tags, s.name AS site_name
        FROM alerts a JOIN clips c ON c.id = a.clip_id JOIN cameras cam ON cam.id = c.camera_id
        JOIN sites s ON s.id = cam.site_id WHERE a.status = ?
        ORDER BY CASE a.severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
                 a.confidence DESC""", (status,))
    st.markdown(f'<p class="lv-note">{len(rows)} {status} alerts. A notification is sent only when you confirm an alert.</p>',
                unsafe_allow_html=True)
    for a in rows[:25]:
        with st.container(border=True):
            left, right = st.columns([3, 2], gap="large")
            with left:
                clip_card({**a, "id": a["clip_id"]})
            with right:
                st.markdown(ui.severity(a["severity"] if status == "pending" else status), unsafe_allow_html=True)
                st.markdown(f"**{ui.HAZARD_NAMES.get(a['hazard_type'], a['hazard_type'])}**, confidence "
                            f"{a['confidence']:.2f}")
                st.caption(f"Rule set: {ui.PROFILE_NAMES.get(a['profile'], a['profile'])}")
                if status == "pending":
                    note = st.text_input("Note (optional)", key=f"n{a['id']}")
                    b1, b2 = st.columns(2)
                    if b1.button("Confirm and notify", key=f"c{a['id']}", type="primary", use_container_width=True):
                        alerts.verify(con, a["id"], True, note)
                        st.toast("Alert confirmed. Notification sent.")
                        st.rerun()
                    if b2.button("Reject", key=f"r{a['id']}", use_container_width=True):
                        alerts.verify(con, a["id"], False, note)
                        st.toast("Alert rejected. No notification sent.")
                        st.rerun()
                else:
                    st.caption(f"Reviewed {when(a['verified_at'])}" + (f": {a['note']}" if a["note"] else ""))
    notes = db.rows(con, "SELECT sent_at, message FROM notifications ORDER BY id DESC LIMIT 10")
    if notes:
        st.subheader("Notifications sent")
        st.dataframe(pd.DataFrame(notes).rename(columns={"sent_at": "Sent", "message": "Message"}),
                     hide_index=True, use_container_width=True)

# ---------------------------------------------------------------- evaluation
with tab_eval:
    if st.button("Recompute"):
        report = evaluate.run(con, index)
    if report:
        cost = report["cost"]
        items = [(cost["clips_total"], "clips indexed", False),
                 (f"{cost['clips_pct_to_vlm']}%", "of clips sent to the VLM", False),
                 (f"{cost['frames_pct_to_vlm']}%", f"of frames sent ({cost['frames_sent_to_vlm']} of {cost['frames_total']})", True)]
        if cost.get("est_tokens_if_all_frames"):
            items.append((f"{100 * (1 - cost['vlm_tokens_in'] / cost['est_tokens_if_all_frames']):.0f}%",
                          "VLM input tokens saved", True))
        if report.get("retrieval"):
            items.append((report["retrieval"]["mean_p_at_k"], f"mean precision at {report['retrieval']['k']}", False))
        st.markdown(ui.kpis(items), unsafe_allow_html=True)

        st.subheader("Hazard detection")
        hrows = []
        for h, v in report["hazards"].items():
            for stage in ("gate_only", "gate_plus_vlm"):
                name = "Gate only" if stage == "gate_only" else ("Gate + VLM" if cost["vlm_tokens_in"]
                                                              else "Gate + VLM (VLM pending, gate fallback)")
                m = v[stage]
                hrows.append({"Hazard": ui.HAZARD_NAMES[h], "Stage": name, "Labelled": v["n_labelled"],
                              "Positives": v["positives"], "Precision": m["precision"], "Recall": m["recall"],
                              "F1": m["f1"]})
        if hrows:
            st.dataframe(pd.DataFrame(hrows), hide_index=True, use_container_width=True)
        st.markdown('<p class="lv-note">Only hazards with 0/1 labels in data/clips.csv are scored. The gate is tuned '
                    'for recall; the VLM pass exists to raise precision.</p>', unsafe_allow_html=True)
        if report.get("retrieval"):
            r = report["retrieval"]
            st.subheader("Search quality")
            st.dataframe(pd.DataFrame(r["queries"]).rename(columns={"query": "Query", "p_at_k": f"P@{r['k']}",
                                                                    "r_at_k": f"R@{r['k']}"}),
                         hide_index=True, use_container_width=True)
    if (ROOT / "docs" / "pipeline.png").exists():
        st.subheader("Pipeline")
        st.image(str(ROOT / "docs" / "pipeline.png"))

# ---------------------------------------------------------------- live check
with tab_live:
    st.markdown('<p class="lv-note">Upload a short clip to run the gate on this server. Clips it marks suspicious '
                'would send at most three frames to the VLM; the rest cost nothing.</p>', unsafe_allow_html=True)
    up = st.file_uploader("Clip (mp4, avi or mov, up to 15 seconds)", type=["mp4", "avi", "mov"])
    if up:
        from lumen.gate import analyze
        with tempfile.NamedTemporaryFile(suffix=Path(up.name).suffix, delete=False) as tmp:
            tmp.write(up.read())
        with st.spinner("Running the gate"):
            res = analyze(tmp.name, zones=[[[0.0, 0.5], [1.0, 0.5], [1.0, 1.0], [0.0, 1.0]]])
        if res is None:
            st.error("This file couldn't be read as video. Upload an mp4, avi or mov file.")
        else:
            n = len(res["frames"])
            st.markdown(ui.kpis([(n, "frames sampled", False), (len(res["suspicious_frames"]), "frames for the VLM", True),
                                 ("Suspicious" if res["suspicious"] else "Clear", "gate verdict", False)]),
                        unsafe_allow_html=True)
            st.dataframe(pd.DataFrame([{"Hazard": ui.HAZARD_NAMES[h], "Gate score": s, "Threshold": GATE_THRESHOLDS[h],
                                        "Flagged": h in res["flagged"]} for h, s in res["gate"].items()]),
                         hide_index=True, use_container_width=True)
            if res["suspicious"]:
                st.image([res["pil"][i] for i in res["suspicious_frames"]], width=280,
                         caption=[f"frame {i}" for i in res["suspicious_frames"]])
            st.caption(f"Detected: {res['tags'] or 'nothing'}. For uploads, the restricted zone is the bottom half of the frame.")
