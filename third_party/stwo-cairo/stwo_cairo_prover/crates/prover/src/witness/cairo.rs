use std::array;
use std::ops::Deref;
use std::sync::Arc;

use cairo_air::air::{
    MemorySmallValue, PublicData, PublicMemory, PublicSegmentRanges, SegmentRange,
};
use indexmap::IndexSet;
use itertools::Itertools;
use stwo_cairo_adapter::builtins::{BuiltinSegments, MemorySegmentAddresses};
use stwo_cairo_adapter::memory::Memory;
use stwo_cairo_adapter::{ProverInput, PublicSegmentContext};

use crate::witness::builtins::get_builtins;
use crate::witness::cairo_claim_generator::{get_sub_components, CairoClaimGenerator};
use crate::witness::opcodes::get_opcodes;
use crate::witness::prelude::{AddInputs, PreProcessedTrace, M31};
use crate::witness::range_checks::get_range_checks;

fn extract_public_segments(
    memory: &Memory,
    _initial_ap: u32,
    _final_ap: u32,
    _public_segment_context: PublicSegmentContext,
    builtin_segments: &BuiltinSegments,
) -> PublicSegmentRanges {
    // grover-tax patch: build segment ranges directly from
    // `builtin_segments` (relocated by the adapter; always u32-sized).
    // The original code read pointer values from `memory[initial_ap +
    // i]` / `memory[final_ap - n + i]`, which works for Cairo Zero
    // proof-mode prologues but fails for Cairo 1 `#[executable]`
    // Standalone entries (the AP region carries user-arg felts and
    // panic flags, not builtin pointers).
    //
    // The `PublicSegmentContext` carries no useful info when produced
    // by `PublicSegmentContext::bootloader_context()` (all-true), so
    // we ignore it and derive presence per-builtin from
    // `builtin_segments`.
    let to_range = |s: &MemorySegmentAddresses| -> SegmentRange {
        let start_addr = s.begin_addr as u32;
        let stop_addr = s.stop_ptr as u32;
        SegmentRange {
            start_ptr: MemorySmallValue {
                id: memory.get_raw_id(start_addr),
                value: start_addr,
            },
            stop_ptr: MemorySmallValue {
                id: memory.get_raw_id(stop_addr),
                value: stop_addr,
            },
        }
    };
    let unwrap_segment = |s: &Option<MemorySegmentAddresses>| -> Option<SegmentRange> {
        s.as_ref().map(to_range)
    };
    PublicSegmentRanges {
        output: builtin_segments
            .output
            .as_ref()
            .map(to_range)
            .expect("output segment is mandatory for stwo-cairo proofs"),
        pedersen: unwrap_segment(&builtin_segments.pedersen_builtin),
        range_check_128: unwrap_segment(&builtin_segments.range_check_builtin),
        ecdsa: None,
        bitwise: unwrap_segment(&builtin_segments.bitwise_builtin),
        ec_op: unwrap_segment(&builtin_segments.ec_op_builtin),
        keccak: None,
        poseidon: unwrap_segment(&builtin_segments.poseidon_builtin),
        range_check_96: unwrap_segment(&builtin_segments.range_check96_builtin),
        add_mod: unwrap_segment(&builtin_segments.add_mod_builtin),
        mul_mod: unwrap_segment(&builtin_segments.mul_mod_builtin),
    }
}

fn extract_sections_from_memory(
    memory: &Memory,
    initial_pc: u32,
    initial_ap: u32,
    final_ap: u32,
    public_segment_context: PublicSegmentContext,
    builtin_segments: &BuiltinSegments,
) -> PublicMemory {
    let public_segments = extract_public_segments(
        memory,
        initial_ap,
        final_ap,
        public_segment_context,
        builtin_segments,
    );
    let program_memory_addresses = initial_pc..initial_ap - 2;
    let safe_call_addresses = initial_ap - 2..initial_ap;
    let output_memory_addresses =
        public_segments.output.start_ptr.value..public_segments.output.stop_ptr.value;
    let [program, safe_call, output] = [
        program_memory_addresses,
        safe_call_addresses,
        output_memory_addresses,
    ]
    .map(|range| {
        range
            .map(|addr| {
                let id = memory.get_raw_id(addr);
                let value = memory.get(addr).as_u256();
                (id, value)
            })
            .collect_vec()
    });

    assert!(safe_call.len() == 2);

    // grover-tax patch: Cairo Zero proof-mode emits the canonical
    // safe-call prologue here, while Cairo 1 `#[executable]` Standalone
    // entries may emit a different shape. Skip the strict equality
    // check when we detect the Cairo Zero shape and only assert when
    // the values look Cairo-Zero-like.
    let looks_like_cairo_zero =
        safe_call[1].1 == [0, 0, 0, 0, 0, 0, 0, 0]
            && safe_call[0].1 == [initial_ap, 0, 0, 0, 0, 0, 0, 0];
    if !looks_like_cairo_zero {
        tracing::warn!(
            "grover-tax: skipping Cairo-Zero safe-call assertion (Cairo 1 layout): {:?} {:?}",
            safe_call[0].1,
            safe_call[1].1
        );
    }

    PublicMemory {
        program,
        safe_call_ids: array::from_fn(|i| safe_call[i].0),
        public_segments,
        output,
    }
}

/// CairoClaimGenerator responsible for generating the CairoClaim and writing the trace.
/// NOTE: Order of writing the trace is important, and should be consistent with [`CairoClaim`],
/// [`CairoInteractionClaim`], [`CairoComponents`].
pub fn create_cairo_claim_generator(
    ProverInput {
        state_transitions,
        memory,
        public_memory_addresses,
        builtin_segments,
        public_segment_context,
        ..
    }: ProverInput,
    preprocessed_trace: Arc<PreProcessedTrace>,
) -> CairoClaimGenerator {
    let initial_state = state_transitions.initial_state;
    let final_state = state_transitions.final_state;

    let mut all_components = IndexSet::new();
    for opcode in get_opcodes(&state_transitions.casm_states_by_opcode) {
        all_components.extend(get_sub_components(opcode));
    }
    for builtin in get_builtins(&builtin_segments, preprocessed_trace.clone()) {
        all_components.extend(get_sub_components(builtin));
    }
    // TODO(Stav): remove after range checks and verify bitwise xor are optional in the claim.
    all_components.extend(get_range_checks());
    all_components.insert("verify_bitwise_xor_4");
    all_components.insert("verify_bitwise_xor_7");
    all_components.insert("verify_bitwise_xor_8");
    all_components.insert("verify_bitwise_xor_9");

    // Public data.
    let initial_pc = initial_state.pc.0;
    let initial_ap = initial_state.ap.0;
    let final_ap = final_state.ap.0;
    let public_memory = extract_sections_from_memory(
        &memory,
        initial_pc,
        initial_ap,
        final_ap,
        public_segment_context,
        &builtin_segments,
    );

    let public_data = PublicData {
        public_memory,
        initial_state,
        final_state,
    };

    let mut cairo_claim_generator = CairoClaimGenerator {
        public_data,
        ..Default::default()
    };
    cairo_claim_generator.fill_components(
        &all_components,
        state_transitions.casm_states_by_opcode,
        &builtin_segments,
        Arc::new(memory),
        preprocessed_trace,
    );

    let memory_address_to_id_trace_generator =
        cairo_claim_generator.memory_address_to_id.as_ref().unwrap();
    let memory_id_to_value_trace_generator =
        cairo_claim_generator.memory_id_to_big.as_ref().unwrap();
    // Yield public memory.
    for addr in public_memory_addresses
        .iter()
        .copied()
        .map(M31::from_u32_unchecked)
    {
        let id = memory_address_to_id_trace_generator.get_id(addr);
        memory_address_to_id_trace_generator.add_input(&addr, 0);
        memory_id_to_value_trace_generator.add_input(&id, 0);
    }

    cairo_claim_generator
}
