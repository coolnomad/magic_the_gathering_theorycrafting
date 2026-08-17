# HOB Phase 6 — Higher-Order Mechanism Modules

- **modules**: 52
- **modules with feedback cycles**: 1
- **by kind**: {'amass': 1, 'discovered_counter': 1, 'discovered_event': 9, 'discovered_obj': 1, 'discovered_resource': 6, 'ferocious': 1, 'gate': 14, 'zone_flow': 1, 'hone_equipment': 1, 'landfall': 1, 'state_constraint': 1, 'recruit': 1, 'saga': 1, 'trigger': 1, 'storied': 1, 'token_production': 11}

## Modules

### Amass  (`amass`)
- anchors: `rule:amass`, `op:amass`, `obj:army-A`, `gate:amass-no-army`
- members: 14  · contributors: 18  · consumers: 6  · conditions: 1  · feedback cycles: 0

### +1/+1 counters  (`discovered_counter`)
- anchors: `counter:+1/+1`
- members: 25  · contributors: 31  · consumers: 0  · conditions: 9  · feedback cycles: 0

### activated-ability trigger  (`discovered_event`)
- anchors: `event:activate-creature-ability`
- members: 2  · contributors: 1  · consumers: 1  · conditions: 1  · feedback cycles: 0

### shared event: event:attack  (`discovered_event`)
- anchors: `event:attack`
- members: 3  · contributors: 2  · consumers: 1  · conditions: 1  · feedback cycles: 0

### counter-placement trigger  (`discovered_event`)
- anchors: `event:counters-placed`
- members: 2  · contributors: 1  · consumers: 1  · conditions: 0  · feedback cycles: 0

### shared event: event:damage  (`discovered_event`)
- anchors: `event:damage`
- members: 2  · contributors: 4  · consumers: 0  · conditions: 1  · feedback cycles: 0

### shared event: event:dies  (`discovered_event`)
- anchors: `event:dies`
- members: 10  · contributors: 8  · consumers: 2  · conditions: 0  · feedback cycles: 0

### life-loss trigger  (`discovered_event`)
- anchors: `event:player-loses-life`
- members: 5  · contributors: 4  · consumers: 1  · conditions: 0  · feedback cycles: 0

### shared event: event:this-creature-dies  (`discovered_event`)
- anchors: `event:this-creature-dies`
- members: 9  · contributors: 8  · consumers: 2  · conditions: 0  · feedback cycles: 0

### shared event: event:this_creature_dies  (`discovered_event`)
- anchors: `event:this_creature_dies`
- members: 9  · contributors: 8  · consumers: 1  · conditions: 0  · feedback cycles: 0

### shared event: event:token-you-control-enters  (`discovered_event`)
- anchors: `event:token-you-control-enters`
- members: 24  · contributors: 23  · consumers: 1  · conditions: 0  · feedback cycles: 0

### shared obj: obj:subtype:elf  (`discovered_obj`)
- anchors: `obj:subtype:elf`
- members: 16  · contributors: 18  · consumers: 0  · conditions: 0  · feedback cycles: 0

### card advantage  (`discovered_resource`)
- anchors: `resource:card`
- members: 6  · contributors: 7  · consumers: 0  · conditions: 2  · feedback cycles: 0

### shared resource: resource:card-in-hand  (`discovered_resource`)
- anchors: `resource:card-in-hand`
- members: 6  · contributors: 7  · consumers: 0  · conditions: 1  · feedback cycles: 0

### shared resource: resource:card_in_hand  (`discovered_resource`)
- anchors: `resource:card_in_hand`
- members: 3  · contributors: 4  · consumers: 0  · conditions: 2  · feedback cycles: 0

### shared resource: resource:cards  (`discovered_resource`)
- anchors: `resource:cards`
- members: 3  · contributors: 4  · consumers: 0  · conditions: 0  · feedback cycles: 0

### life swing  (`discovered_resource`)
- anchors: `resource:life`
- members: 11  · contributors: 12  · consumers: 0  · conditions: 2  · feedback cycles: 0

### mana base  (`discovered_resource`)
- anchors: `resource:mana`
- members: 11  · contributors: 14  · consumers: 0  · conditions: 1  · feedback cycles: 0

### Ferocious  (`ferocious`)
- anchors: `rule:ferocious`, `keyword:ferocious`
- members: 6  · contributors: 4  · consumers: 1  · conditions: 0  · feedback cycles: 0

### gate:amass-no-army  (`gate`)
- anchors: `gate:amass-no-army`
- members: 0  · contributors: 1  · consumers: 1  · conditions: 1  · feedback cycles: 0

### gate:completeness:sac-cost:face:008a11c1-d283-49fe-abd7-ff4fe8b1fe79:0  (`gate`)
- anchors: `gate:completeness:sac-cost:face:008a11c1-d283-49fe-abd7-ff4fe8b1fe79:0`
- members: 0  · contributors: 0  · consumers: 1  · conditions: 3  · feedback cycles: 0

### gate:completeness:sac-cost:face:0ea58cfe-b37c-49a6-a3be-7e60065b8238:0  (`gate`)
- anchors: `gate:completeness:sac-cost:face:0ea58cfe-b37c-49a6-a3be-7e60065b8238:0`
- members: 0  · contributors: 0  · consumers: 1  · conditions: 3  · feedback cycles: 0

### gate:completeness:sac-cost:face:2e728381-6db0-4c66-883d-82d718fef833:1  (`gate`)
- anchors: `gate:completeness:sac-cost:face:2e728381-6db0-4c66-883d-82d718fef833:1`
- members: 0  · contributors: 0  · consumers: 1  · conditions: 2  · feedback cycles: 0

### gate:completeness:sac-cost:face:88522a0f-5377-4522-97f4-4148bef954af:0  (`gate`)
- anchors: `gate:completeness:sac-cost:face:88522a0f-5377-4522-97f4-4148bef954af:0`
- members: 0  · contributors: 0  · consumers: 1  · conditions: 3  · feedback cycles: 0

### gate:completeness:sac-cost:face:8d88facd-cf7e-498e-ab6b-6bd021316162:0  (`gate`)
- anchors: `gate:completeness:sac-cost:face:8d88facd-cf7e-498e-ab6b-6bd021316162:0`
- members: 0  · contributors: 0  · consumers: 2  · conditions: 2  · feedback cycles: 0

### gate:completeness:sac-cost:face:cfaa8b7b-7bfc-4660-bbc7-a717e05df6ef:0  (`gate`)
- anchors: `gate:completeness:sac-cost:face:cfaa8b7b-7bfc-4660-bbc7-a717e05df6ef:0`
- members: 0  · contributors: 0  · consumers: 1  · conditions: 2  · feedback cycles: 0

### gate:completeness:sac-cost:face:dda607bd-f419-4b7f-b052-a5ce6ce22bfe:0  (`gate`)
- anchors: `gate:completeness:sac-cost:face:dda607bd-f419-4b7f-b052-a5ce6ce22bfe:0`
- members: 1  · contributors: 1  · consumers: 2  · conditions: 2  · feedback cycles: 0

### gate:completeness:sac-cost:face:e3a665f9-6e51-4e0d-923b-e9552d5978a4:0  (`gate`)
- anchors: `gate:completeness:sac-cost:face:e3a665f9-6e51-4e0d-923b-e9552d5978a4:0`
- members: 0  · contributors: 0  · consumers: 2  · conditions: 3  · feedback cycles: 0

### gate:completeness:sac-cost:face:fdf7f144-56e4-4f88-b81a-b85473922355:0  (`gate`)
- anchors: `gate:completeness:sac-cost:face:fdf7f144-56e4-4f88-b81a-b85473922355:0`
- members: 0  · contributors: 0  · consumers: 2  · conditions: 3  · feedback cycles: 0

### gate:or-cost:face:dda607bd-f419-4b7f-b052-a5ce6ce22bfe:0  (`gate`)
- anchors: `gate:or-cost:face:dda607bd-f419-4b7f-b052-a5ce6ce22bfe:0`
- members: 1  · contributors: 0  · consumers: 2  · conditions: 0  · feedback cycles: 0

### gate:recruit-nonland-discard  (`gate`)
- anchors: `gate:recruit-nonland-discard`
- members: 0  · contributors: 1  · consumers: 1  · conditions: 1  · feedback cycles: 0

### gate:second-draw  (`gate`)
- anchors: `gate:second-draw`
- members: 0  · contributors: 1  · consumers: 3  · conditions: 1  · feedback cycles: 0

### gate:storied  (`gate`)
- anchors: `gate:storied`
- members: 74  · contributors: 81  · consumers: 17  · conditions: 1  · feedback cycles: 0

### graveyard reuse  (`zone_flow`)
- anchors: `zone:graveyard`
- members: 42  · contributors: 54  · consumers: 0  · conditions: 5  · feedback cycles: 0

### Hone/Equipment  (`hone_equipment`)
- anchors: `counter:hone`, `rule:hone`, `rule:equip`, `keyword:equip`
- members: 13  · contributors: 31  · consumers: 0  · conditions: 0  · feedback cycles: 0

### Landfall  (`landfall`)
- anchors: `rule:landfall`, `keyword:landfall`
- members: 9  · contributors: 8  · consumers: 0  · conditions: 0  · feedback cycles: 0

### legend rule (state-based action)  (`state_constraint`)
- anchors: `state:legend-conflict:azog-moria-s-ruin`, `state:legend-conflict:balin-loremaster`, `state:legend-conflict:bard-king-of-dale`, `state:legend-conflict:bard-the-bowman`, `state:legend-conflict:belladonna-took`, `state:legend-conflict:beorn-reluctant-host`, `state:legend-conflict:beorn-the-fierce`, `state:legend-conflict:bifur-melodic-rider`, `state:legend-conflict:bilbo-baggins-burglar`, `state:legend-conflict:bilbo-luckwearer`, `state:legend-conflict:bilbo-thief-in-the-night`, `state:legend-conflict:bofur-reliable-guardian`, `state:legend-conflict:bolg-of-the-north`, `state:legend-conflict:bombur-gentle-dreamer`, `state:legend-conflict:d-in-ironfoot`, `state:legend-conflict:d-in-lord-of-the-iron-hills`, `state:legend-conflict:dori-bearer-of-friends`, `state:legend-conflict:dwalin-weaponmaster`, `state:legend-conflict:elrond-moon-reader`, `state:legend-conflict:f-li-the-pathfinder`, `state:legend-conflict:galion-elvenking-s-butler`, `state:legend-conflict:gandalf-goblins-bane`, `state:legend-conflict:gandalf-spark-starter`, `state:legend-conflict:gandalf-wandering-wizard`, `state:legend-conflict:gl-in-the-mighty`, `state:legend-conflict:glamdring-foe-hammer`, `state:legend-conflict:gollum-riddle-master`, `state:legend-conflict:gollum-silent-slinker`, `state:legend-conflict:gollum-the-abandoned`, `state:legend-conflict:in-the-brave`, `state:legend-conflict:k-li-the-resourceful`, `state:legend-conflict:my-precious`, `state:legend-conflict:nori-teller-of-tales`, `state:legend-conflict:orcrist-goblin-cleaver`, `state:legend-conflict:ori-keeper-of-songs`, `state:legend-conflict:radagast-of-rhosgobel`, `state:legend-conflict:smaug-the-great-calamity`, `state:legend-conflict:smaug-the-magnificent`, `state:legend-conflict:smaug-wicked-worm`, `state:legend-conflict:sting-bilbo-s-sword`, `state:legend-conflict:the-arkenstone`, `state:legend-conflict:the-black-arrow`, `state:legend-conflict:the-chief-warg`, `state:legend-conflict:the-great-goblin`, `state:legend-conflict:the-lord-of-the-eagles`, `state:legend-conflict:the-master-of-lake-town`, `state:legend-conflict:the-notary-hobbits`, `state:legend-conflict:the-queen-of-dale`, `state:legend-conflict:the-sackville-bagginses`, `state:legend-conflict:thorin-mountain-king`, `state:legend-conflict:thorin-oakenshield`, `state:legend-conflict:thr-r-s-map`, `state:legend-conflict:thranduil-sindarin-liege`, `state:legend-conflict:thranduil-the-elvenking`, `state:legend-conflict:tom-bert-and-william`
- members: 55  · contributors: 55  · consumers: 55  · conditions: 0  · feedback cycles: 0

### Recruit  (`recruit`)
- anchors: `rule:recruit`, `gate:recruit-nonland-discard`
- members: 10  · contributors: 12  · consumers: 1  · conditions: 2  · feedback cycles: 0

### Saga  (`saga`)
- anchors: `rule:saga`, `counter:lore`
- members: 8  · contributors: 19  · consumers: 0  · conditions: 0  · feedback cycles: 0

### second-draw triggers  (`trigger`)
- anchors: `event:card-drawn`, `event:draw`, `event:draw-second-card`, `event:draw-second-card-each-turn`, `event:draw_second_card_each_turn`, `event:player_draws_card`, `event:you_draw_a_card`
- members: 9  · contributors: 8  · consumers: 5  · conditions: 2  · feedback cycles: 0

### Storied  (`storied`)
- anchors: `gate:storied`, `state:enduring_story`, `rule:storied`
- members: 74  · contributors: 107  · consumers: 33  · conditions: 5  · feedback cycles: 1
  - cycle: state:enduring_story → state:enduring_story

### token production (token:axe)  (`token_production`)
- anchors: `token:axe`
- members: 2  · contributors: 2  · consumers: 6  · conditions: 0  · feedback cycles: 0

### token production (token:bear)  (`token_production`)
- anchors: `token:bear`
- members: 1  · contributors: 1  · consumers: 2  · conditions: 0  · feedback cycles: 0

### token production (token:bird-soldier)  (`token_production`)
- anchors: `token:bird-soldier`
- members: 1  · contributors: 2  · consumers: 3  · conditions: 0  · feedback cycles: 0

### token production (token:copy)  (`token_production`)
- anchors: `token:copy`
- members: 1  · contributors: 1  · consumers: 0  · conditions: 1  · feedback cycles: 0

### token production (token:dragon)  (`token_production`)
- anchors: `token:dragon`
- members: 1  · contributors: 1  · consumers: 2  · conditions: 1  · feedback cycles: 0

### token production (token:dwarf)  (`token_production`)
- anchors: `token:dwarf`
- members: 4  · contributors: 5  · consumers: 2  · conditions: 0  · feedback cycles: 0

### token production (token:elf)  (`token_production`)
- anchors: `token:elf`
- members: 2  · contributors: 2  · consumers: 2  · conditions: 1  · feedback cycles: 0

### token production (token:human-soldier)  (`token_production`)
- anchors: `token:human-soldier`
- members: 10  · contributors: 1  · consumers: 3  · conditions: 1  · feedback cycles: 0

### token production (token:stone-boulder)  (`token_production`)
- anchors: `token:stone-boulder`
- members: 1  · contributors: 1  · consumers: 4  · conditions: 1  · feedback cycles: 0

### token production (token:treasure)  (`token_production`)
- anchors: `token:treasure`
- members: 10  · contributors: 15  · consumers: 4  · conditions: 4  · feedback cycles: 0

### token production (token:wolf)  (`token_production`)
- anchors: `token:wolf`
- members: 2  · contributors: 3  · consumers: 2  · conditions: 0  · feedback cycles: 0

