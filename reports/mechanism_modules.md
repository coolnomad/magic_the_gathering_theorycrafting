# HOB Phase 6 — Higher-Order Mechanism Modules

- **modules**: 22
- **modules with feedback cycles**: 1
- **by kind**: {'amass': 1, 'ferocious': 1, 'gate': 3, 'zone_flow': 1, 'hone_equipment': 1, 'landfall': 1, 'recruit': 1, 'saga': 1, 'trigger': 1, 'storied': 1, 'token_production': 10}

## Modules

### Amass  (`amass`)
- anchors: `rule:amass`, `op:amass`, `obj:army-A`, `gate:amass-no-army`
- members: 14  · contributors: 18  · consumers: 6  · conditions: 1  · feedback cycles: 0

### Ferocious  (`ferocious`)
- anchors: `rule:ferocious`, `keyword:ferocious`
- members: 6  · contributors: 4  · consumers: 1  · conditions: 0  · feedback cycles: 0

### gate:amass-no-army  (`gate`)
- anchors: `gate:amass-no-army`
- members: 0  · contributors: 1  · consumers: 1  · conditions: 1  · feedback cycles: 0

### gate:recruit-nonland-discard  (`gate`)
- anchors: `gate:recruit-nonland-discard`
- members: 0  · contributors: 1  · consumers: 1  · conditions: 1  · feedback cycles: 0

### gate:storied  (`gate`)
- anchors: `gate:storied`
- members: 74  · contributors: 81  · consumers: 17  · conditions: 1  · feedback cycles: 0

### graveyard reuse  (`zone_flow`)
- anchors: `zone:graveyard`
- members: 25  · contributors: 31  · consumers: 0  · conditions: 5  · feedback cycles: 0

### Hone/Equipment  (`hone_equipment`)
- anchors: `counter:hone`, `rule:hone`, `rule:equip`, `keyword:equip`
- members: 13  · contributors: 18  · consumers: 0  · conditions: 0  · feedback cycles: 0

### Landfall  (`landfall`)
- anchors: `rule:landfall`, `keyword:landfall`
- members: 9  · contributors: 8  · consumers: 0  · conditions: 0  · feedback cycles: 0

### Recruit  (`recruit`)
- anchors: `rule:recruit`, `gate:recruit-nonland-discard`
- members: 10  · contributors: 12  · consumers: 1  · conditions: 2  · feedback cycles: 0

### Saga  (`saga`)
- anchors: `rule:saga`, `counter:lore`
- members: 8  · contributors: 19  · consumers: 0  · conditions: 0  · feedback cycles: 0

### second-draw triggers  (`trigger`)
- anchors: `event:card-drawn`, `event:draw`, `event:draw-second-card`, `event:draw-second-card-each-turn`, `event:draw_second_card_each_turn`, `event:player_draws_card`, `event:you_draw_a_card`
- members: 9  · contributors: 5  · consumers: 5  · conditions: 2  · feedback cycles: 0

### Storied  (`storied`)
- anchors: `gate:storied`, `state:enduring_story`, `rule:storied`
- members: 74  · contributors: 107  · consumers: 33  · conditions: 5  · feedback cycles: 1
  - cycle: state:enduring_story → state:enduring_story

### token production (token:axe)  (`token_production`)
- anchors: `token:axe`
- members: 2  · contributors: 2  · consumers: 4  · conditions: 0  · feedback cycles: 0

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

### token production (token:stone-boulder)  (`token_production`)
- anchors: `token:stone-boulder`
- members: 1  · contributors: 1  · consumers: 4  · conditions: 1  · feedback cycles: 0

### token production (token:treasure)  (`token_production`)
- anchors: `token:treasure`
- members: 10  · contributors: 15  · consumers: 4  · conditions: 4  · feedback cycles: 0

### token production (token:wolf)  (`token_production`)
- anchors: `token:wolf`
- members: 2  · contributors: 2  · consumers: 2  · conditions: 0  · feedback cycles: 0

