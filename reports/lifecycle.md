# HOB Executability Layer — Lifecycle Transitions + OR Cost Gates (pt7)

- **lifecycle nodes**: 16  · **edges**: 54
- **attachment states with a leave-battlefield termination**: 13
- **explicit OR cost gates**: 1
- new schema-extension predicates: `TERMINATES` (Op/Event/State → State), `HAS_ALTERNATIVE` (Gate → Gate/Cost/Operation)

## General invariant

`rule:leave-battlefield-terminates-attachment` — when a permanent leaves the battlefield, terminate every attachment state it hosts and every continuous effect requiring that state.

## Sample transitions

- `op:leave-battlefield:face:2802069f-201e-43a7-b5d3-43a95951a2ec:0` TERMINATES `state:attachment:face:2802069f-201e-43a7-b5d3-43a95951a2ec:0`
- `op:leave-battlefield:face:2e728381-6db0-4c66-883d-82d718fef833:0` TERMINATES `state:attachment:face:2e728381-6db0-4c66-883d-82d718fef833:0`
- `op:leave-battlefield:face:30c3c700-46f4-4a77-8c45-5c7e3a21bd62:0` TERMINATES `state:attachment:face:30c3c700-46f4-4a77-8c45-5c7e3a21bd62:0`
- `op:leave-battlefield:face:3cc333a1-c854-4b7c-8002-910e48222371:0` TERMINATES `state:attachment:face:3cc333a1-c854-4b7c-8002-910e48222371:0`
- `op:leave-battlefield:face:9779f32c-b1a2-42a3-8e78-14c28c3ad254:0` TERMINATES `state:attachment:face:9779f32c-b1a2-42a3-8e78-14c28c3ad254:0`
- `op:leave-battlefield:face:9cc52afb-9788-46f6-9f9b-347513f8a64f:0` TERMINATES `state:attachment:face:9cc52afb-9788-46f6-9f9b-347513f8a64f:0`
- `op:leave-battlefield:face:bb67d0a4-864e-4f46-8538-fdd920bf0197:0` TERMINATES `state:attachment:face:bb67d0a4-864e-4f46-8538-fdd920bf0197:0`
- `op:leave-battlefield:face:cb2803ee-825b-420e-b404-c7c44f15ec15:0` TERMINATES `state:attachment:face:cb2803ee-825b-420e-b404-c7c44f15ec15:0`
- `op:leave-battlefield:face:cc65821a-1893-4087-b461-35cf9fd26c71:0` TERMINATES `state:attachment:face:cc65821a-1893-4087-b461-35cf9fd26c71:0`
- `op:leave-battlefield:face:eda99a16-6a7c-4f39-8a6b-a284e6afd3fc:0` TERMINATES `state:attachment:face:eda99a16-6a7c-4f39-8a6b-a284e6afd3fc:0`
- `op:leave-battlefield:face:eec81460-899d-4b4c-b33c-ce2ca704df17:0` TERMINATES `state:attachment:face:eec81460-899d-4b4c-b33c-ce2ca704df17:0`
- `op:leave-battlefield:face:f75bb13b-41fc-4614-b35e-f456069ce9c6:0` TERMINATES `state:attachment:face:f75bb13b-41fc-4614-b35e-f456069ce9c6:0`
- `op:leave-battlefield:token:axe` TERMINATES `state:attachment:token:axe`
