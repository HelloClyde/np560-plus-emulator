/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Exact first-match index of the original 191-slot application observer.
 * This is diagnostic dispatch only: it does not classify or modify guest code.
 * Keep indices stable; scripts/fixtures/np560_application_observer_sites.json
 * records the pre-optimization ordering, including its shadowed duplicate.
 */
#ifndef DMCU_OBSERVER_SITES_H
#define DMCU_OBSERVER_SITES_H

static inline unsigned dmcu_application_trace_index(uint32_t address)
{
    switch (address) {
    case 0x2d7dd2u: return 0; /* recovered top-level application dispatcher */
    case 0x2d7e52u: return 1; /* return from the one-shot application initializer */
    case 0x2b2f44u: return 2; /* system/storage registry initializer */
    case 0x2d7f06u: return 3; /* return from the system/storage registry initializer */
    case 0x2d7f44u: return 4; /* return from 31:706a */
    case 0x2d7f48u: return 5; /* return from 33:4ee2 */
    case 0x2d7f4cu: return 6; /* return from 33:0fd6 */
    case 0x2d7f62u: return 7; /* return from 29:13dc */
    case 0x2d7f66u: return 8; /* return from 32:cfcc */
    case 0x2d7f6au: return 9; /* return from 33:6f30 */
    case 0x2d7f7cu: return 10; /* return from 32:f47a */
    case 0x2902d8u: return 11; /* storage-capacity scan */
    case 0x229738u: return 12; /* one-shot application initializer */
    case 0x22515eu: return 13; /* application main loop */
    case 0x225170u: return 14; /* return from 32:9a9a */
    case 0x225174u: return 15; /* return from 33:65c0 */
    case 0x225188u: return 16; /* return from 29:13dc */
    case 0x22518eu: return 17; /* return from 33:6f3c */
    case 0x225192u: return 18; /* return from 32:c86e */
    case 0x22519eu: return 19; /* return from 2d:b54c */
    case 0x2251aau: return 20; /* return from 32:50ba */
    case 0x2251b4u: return 21; /* return from 33:4a84 */
    case 0x2251bau: return 22; /* return from 32:f65a */
    case 0x2251beu: return 23; /* return from 08:4360 */
    case 0x32512cu: return 24; /* resource FILE driver */
    case 0x2ebe2eu: return 25; /* resource FILE attach */
    case 0x2ebe42u: return 26; /* resource attach: return from file-size query */
    case 0x2ebe6eu: return 27; /* resource attach: return from resident file open */
    case 0x2ebf4eu: return 28; /* resource attach: return from first path check */
    case 0x2ebf72u: return 29; /* resource attach: return from second path check */
    case 0x2ebf94u: return 30; /* resource attach: common return */
    case 0x30c99eu: return 31; /* file-size trampoline */
    case 0x31339au: return 32; /* file-size record scanner entry */
    case 0x3133c8u: return 33; /* file-size scanner: return from path resolver */
    case 0x3133d0u: return 34; /* file-size scanner: path resolver failed */
    case 0x3133f6u: return 35; /* file-size scanner: return from directory record scan */
    case 0x313424u: return 36; /* file-size scanner: record/attribute failure */
    case 0x31343cu: return 37; /* file-size scanner: valid regular-file record */
    case 0x31345au: return 38; /* file-size scanner: common return */
    case 0x30c9a2u: return 39; /* resident-file-open wrapper */
    case 0x1bce3cu: return 40; /* resident resource initializer */
    case 0x23a38cu: return 41; /* exact application-context selector */
    case 0x1bd492u: return 42; /* return from application-context selector */
    case 0x1f1f1au: return 43; /* resident filesystem open routine */
    case 0x333376u: return 44; /* hardware-state predicate before application loop */
    case 0xe75bau: return 45; /* non-returning resident application loop */
    case 0x22522au: return 46; /* loop: return from 32:f65a */
    case 0x22522eu: return 47; /* loop: return from 30:8c1c */
    case 0x225232u: return 48; /* loop: return from 33:5090 */
    case 0x225236u: return 49; /* loop: return from 33:4ef8 */
    case 0x22523au: return 50; /* loop: return from 33:5d76 */
    case 0x22542au: return 51; /* loop: return from 32:2930 */
    case 0x22542eu: return 52; /* loop: return from 32:342e */
    case 0x225432u: return 53; /* loop: return from 33:4ee2 */
    case 0x225436u: return 54; /* loop: return from 33:43ce */
    case 0x336f30u: return 55; /* top-level post-registry hook entry */
    case 0x32f47au: return 56; /* top-level timer/config entry */
    case 0x30084u: return 57; /* inferred scheduler: return from top-level dispatcher */
    case 0x2d7f80u: return 58; /* unexpected return from non-returning application loop */
    case 0x334f50u: return 59; /* factory linked reset preamble */
    case 0x33603cu: return 60; /* factory linked SP/FP/compiler-start preamble */
    case 0x114560u: return 61; /* linked 261-descriptor compiler initializer */
    case 0x77fe4u: return 62; /* linked nine-descriptor constant initializer */
    case 0x3026au: return 63; /* linked exact system main */
    case 0x2e2e82u: return 64; /* shared compiler epilogue: identify the unwinding caller */
    case 0x31d3bau: return 65; /* foreground copy helper: capture caller and arguments */
    case 0x2fc59au: return 66; /* foreground parent reached from the main status loop */
    case 0x5f16f6u: return 67; /* relocated foreground context/status predicate */
    case 0x31345eu: return 68; /* foreground asynchronous-state branch */
    case 0x22381eu: return 69; /* alternate foreground asynchronous-state branch */
    case 0x202de0u: return 70; /* foreground UI/event loop */
    case 0x20be12u: return 71; /* modal loading task entry */
    case 0x20bee0u: return 72; /* modal loading task event-loop head */
    case 0x20bf00u: return 73; /* return from the resident event dispatcher */
    case 0x20c336u: return 74; /* modal loading task exit path */
    case 0x8441au: return 75; /* resident byte-fill primitive */
    case 0x301a54u: return 76; /* rectangle/region compositor entry */
    case 0x332562u: return 77; /* foreground event-gate entry */
    case 0x202e30u: return 78; /* return from the foreground event gate */
    case 0x324c34u: return 79; /* foreground event-ready predicate */
    case 0x202e34u: return 80; /* return from the event-ready predicate */
    case 0x295126u: return 81; /* installed cursor/redraw refresh routine */
    case 0x294c86u: return 82; /* unrelated flat JPEG-parser exit; should be unreachable */
    case 0x294df4u: return 83; /* unrelated flat JPEG-parser entry; should be unreachable */
    case 0x334eccu: return 84; /* exact matrix-index to application-event mapper */
    case 0x202e9eu: return 85; /* foreground return from the event mapper */
    case 0x277d8au: return 86; /* resource/text stream worker reached through callback */
    case 0x334510u: return 87; /* outer resident event-handler dispatch */
    case 0x300a6u: return 88; /* return to the caller-constrained outer event loop */
    case 0x2b9178u: return 89; /* application root-object constructor */
    case 0x279892u: return 90; /* parent which invokes the root-object constructor */
    case 0x503870u: return 91; /* one-valued wrapper around the constructor parent */
    case 0x503892u: return 92; /* zero-valued wrapper around the constructor parent */
    case 0x325accu: return 93; /* validation checksum which guards resource decoding */
    case 0x335906u: return 94; /* mode-mask helper: diagnose its far return frame */
    case 0x33529eu: return 95; /* flat shared epilogue entered by outer paths */
    case 0x3352aau: return 96; /* flat large copy/convert body: diagnose its caller */
    case 0x3357e2u: return 97; /* flat copy/convert shared entry A */
    case 0x335b9au: return 98; /* flat copy/convert shared entry B */
    case 0x3358dau: return 99; /* flat copy/convert shared callback path */
    case 0x1fb496u: return 100; /* resident application-event dispatcher */
    case 0x1b23f4u: return 101; /* return from first operation-0x0b table allocation */
    case 0x1b2400u: return 102; /* first operation-0x0b allocation succeeded */
    case 0x1b2c46u: return 103; /* operation-0x0b cleanup path */
    case 0x2578eau: return 104; /* heap walker requests a descriptor bit */
    case 0x2578eeu: return 105; /* return from descriptor-bit allocator */
    case 0x2579aau: return 106; /* heap descriptor allocation failed */
    case 0x30251eu: return 107; /* descriptor-bit allocator entry */
    case 0x302624u: return 108; /* descriptor-bit allocator exhausted */
    case 0x302626u: return 109; /* descriptor-bit allocator epilogue */
    case 0x31f2d8u: return 110; /* modal loop return from low-level event helper */
    case 0x31f2feu: return 111; /* modal loop accepted an event and is exiting */
    case 0x32c476u: return 112; /* modal-object cleanup wrapper */
    case 0x2b758eu: return 113; /* shared cleanup tail entered with the caller's frame */
    case 0x2b54e6u: return 114; /* continuation selected by the shared cleanup tail */
    case 0x2885eeu: return 115; /* first helper called by the shared cleanup tail */
    case 0x203390u: return 116; /* second helper called by the shared cleanup tail */
    case 0x2894c2u: return 117; /* result/resource scanner entry */
    case 0x3351e0u: return 118; /* result scanner resource-handle lookup wrapper */
    case 0x3351f2u: return 119; /* result scanner handle-to-pointer wrapper */
    case 0x3366e2u: return 120; /* display/state refresh thunk */
    case 0x318f74u: return 121; /* result-record preparation/sort wrapper */
    case 0x241f02u: return 122; /* shared byte-sort tail */
    case 0x2ed34au: return 123; /* exact post-foreground launch sequence */
    case 0x2ed38au: return 124; /* return from first launch FILE open */
    case 0x2ed3c0u: return 125; /* return from second launch FILE open */
    case 0x2ed3e0u: return 126; /* return from launch FILE-size wrapper */
    case 0x2ed404u: return 127; /* null primary FILE branch */
    case 0x2ed420u: return 128; /* primary FILE opened; enter launch-manager path */
    case 0x1821f4u: return 129; /* exact resident application launch manager */
    case 0x18232au: return 130; /* return from launch-manager resource opener */
    case 0x2fe4c8u: return 131; /* application-code registry lookup */
    case 0x1824aau: return 132; /* return from application-code registry lookup */
    case 0x2ed456u: return 133; /* return from resident launch manager */
    case 0x2ed4a6u: return 134; /* launch sequence common epilogue */
    case 0x2cc9e8u: return 135; /* exact generic-menu application entry */
    case 0x2cca00u: return 136; /* generic menu: descriptor page decoded */
    case 0x2ccb32u: return 137; /* generic menu: return from page-table builder */
    case 0x2ccb48u: return 138; /* generic menu: null page-table failure path */
    case 0x2ccb5au: return 139; /* generic menu: valid page-table success path */
    case 0x2ccbb2u: return 140; /* generic menu: return from layout/string copy */
    case 0x2ccbb6u: return 141; /* generic menu: return from menu event handler */
    case 0x2ccbc2u: return 142; /* generic menu: cleanup complete */
    case 0x2a322au: return 143; /* exact menu page-table builder entry */
    case 0x2a327cu: return 144; /* page builder: static maximum-page decoded */
    case 0x2a32f2u: return 145; /* page builder: dynamic maximum-page decoded */
    case 0x2a330au: return 146; /* page builder: requested page is valid */
    case 0x2a335au: return 147; /* page builder: resident static pointer path */
    case 0x2a3376u: return 148; /* page builder: first packed pointer decoded */
    case 0x2a33aau: return 149; /* page builder: successor packed pointer decoded */
    case 0x2a33b8u: return 150; /* page builder: resource-backed pointer path */
    case 0x2a3492u: return 151; /* page builder: successful result */
    case 0x2aa75au: return 152; /* return from resident FILE open in validation */
    case 0x25ce1eu: return 153; /* return from the validation/file-open wrapper */
    case 0x2d78b6u: return 154; /* allocator: return from first readiness predicate */
    case 0x2d78d6u: return 155; /* allocator: return from second readiness predicate */
    case 0x2d79b0u: return 156; /* allocator: return from capacity preparation */
    case 0x2d79e2u: return 157; /* allocator: return from heap allocation */
    case 0x2d7a12u: return 158; /* allocator: return from storage status query */
    case 0x25ce2eu: return 159; /* return from the resource allocator */
    case 0x31f6aeu: return 160; /* storage update: return from unit initialization */
    case 0x31f6c4u: return 161; /* storage update: return from maintenance pass */
    case 0x31f6dau: return 162; /* storage update: return from final commit */
    case 0x2aa952u: return 163; /* exact factory-default/catalogue routine entry */
    case 0x2d8134u: return 164; /* caller return from factory-default/catalogue routine */
    case 0x330070u: return 165; /* text dispatcher: capture bad modal text-pointer caller */
    case 0x32082eu: return 166; /* record/text adapter: capture the bad source record */
    case 0x2d7facu: return 167; /* return from persistent startup-selector byte read */
    case 0x3343deu: return 168; /* return from persistent startup-selector routine */
    /* Exact 1E:F734 modal-input worker boundaries.  These distinguish
     * the generic-event guard, resident application dispatch and both
     * result arms for event 0x86 without modifying the event queue. */
    case 0x1ef8e4u: return 169; /* mapped event copied into the worker dispatch local */
    case 0x1efc56u: return 170; /* generic modal-event path */
    case 0x335b70u: return 171; /* generic modal-event guard */
    case 0x1efc5au: return 172; /* return from the generic modal-event guard */
    case 0x1efc62u: return 173; /* guard accepted the event */
    case 0x1efce4u: return 174; /* guard rejected the event / generic result path */
    case 0x1efc6cu: return 175; /* return from the resident application dispatcher */
    case 0x1efccau: return 176; /* resident application dispatcher returned zero */
    case 0x1efc74u: return 177; /* resident application dispatcher returned nonzero */
    case 0x1efd74u: return 178; /* common modal-worker result */
    /* Read-only foreground-cycle boundaries.  These retain the value in
     * R0 at each producer/consumer boundary without changing the event
     * queue, application selector, or guest timing. */
    case 0x202e12u: return 179; /* return from the raw foreground event source */
    /* Slot 180 (0x202e9eu) is shadowed by its earlier duplicate. */
    case 0x1df2ecu: return 181; /* exact resident root-menu controller entry */
    case 0x1df6d8u: return 182; /* root controller item-loop decision point */
    case 0x1df900u: return 183; /* item loop skipped after the ULE comparison */
    case 0x10e4aau: return 184; /* exact resident hierarchy root-menu renderer entry */
    case 0x202f16u: return 185; /* event word copied into the decoder local */
    case 0x203190u: return 186; /* state-transition flag loaded from frame -0x16 */
    case 0x203388u: return 187; /* foreground loop exit selected by global 51:2250 */
    case 0x31f2b2u: return 188; /* return from the modal event-ready predicate */
    case 0x31f282u: return 189; /* exact modal event-loop entry and its calling frame */
    case 0x31f2aeu: return 190; /* first direct transfer into the modal loop body */
    default: return DMCU_APPLICATION_TRACE_ENTRIES;
    }
}

#endif

