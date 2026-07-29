---
description: Create a new project — repo, board, protections, labels — then wire baton to it
---
Activate the baton-bootstrap skill to create a new project: $ARGUMENTS

Follow the baton-bootstrap workflow: confirm the parameters with the user, create the
repo and the board with the ADMIN credential, apply branch protections and label axes,
then `baton init` to write `.baton/config.yaml` and `baton doctor` to prove discovery
reaches the board. Admin credential is required — do not fall back to the agent one.
