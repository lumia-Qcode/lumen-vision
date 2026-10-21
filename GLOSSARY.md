# Glossary — Lumen Vision

**Clip** — A single short (≤15 s) CCTV recording from one Camera. The unit of storage, search results, and alerts.

**Camera** — A fixed viewpoint at a Site. Owns zero or more Zones.

**Site** — A physical telecom location (e.g. a remote tower compound, a staffed exchange). Every Camera belongs to one Site.

**Site Profile** — The rule set a Site is governed by. Two exist: *Unmanned Tower* (any person present is notable) and *Staffed Hub* (people expected; only after-hours or restricted-zone presence is notable).

**Zone** — A region of a Camera's view marked as restricted (e.g. shelter door, battery cabinet, tower base).

**Observation** — Something directly visible in a Clip: fire visible, smoke visible, person inside a Zone, an object present then absent. The system may assert Observations automatically.

**Interpretation** — A higher-level claim about meaning or intent (theft, sabotage, trespass with intent). Never asserted automatically; only shown as a candidate for a human to judge.

**Hazard Flag** — A confidence-scored Observation of one of the three MVP hazard types: *fire/smoke*, *restricted-zone entry*, *removed/abandoned object*.

**Gate** — The cheap first-pass screen run on every Clip that decides which Clips are Suspicious.

**Suspicious Frame** — A frame the Gate selects as worth sending to the vision-language model.

**Alert** — A Hazard Flag that, under the Site's Profile, warrants human attention. Starts *pending*; becomes *confirmed* or *rejected* by a Verifier.

**Verification** — The human decision on a pending Alert. A Notification is sent only after confirmation.

**Notification** — The outbound message produced by a confirmed Alert.
