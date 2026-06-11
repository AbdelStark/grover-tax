//! `kmx` — a small CLI mirroring upstream's `example_sample` / `example_fuzz`
//! (KB-8, #120), for parity-checking the simulator against the reference.
//!
//! Usage:
//!   kmx sample <file.kmx> <v0> [v1 ...]   # load registers r0.. := v0.., run, print outputs
//!   kmx fuzz   <file.kmx> [--shots N] [--seed S] < cases   # cases: "a b -> c d" per line

use std::io::Read;
use std::process::ExitCode;

use kickmix::{
    check_case, fuzz, load_register, read_register, run, Circuit, FuzzCase, SplitMix64, State,
};

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    match args.first().map(String::as_str) {
        Some("sample") => cmd_sample(&args[1..]),
        Some("fuzz") => cmd_fuzz(&args[1..]),
        _ => {
            eprintln!("usage: kmx <sample|fuzz> <file.kmx> ...");
            ExitCode::from(2)
        }
    }
}

fn load_circuit(path: &str) -> Result<Circuit, ExitCode> {
    let text = std::fs::read_to_string(path).map_err(|e| {
        eprintln!("cannot read {path}: {e}");
        ExitCode::from(2)
    })?;
    Circuit::parse(&text).map_err(|e| {
        eprintln!("parse error: {e}");
        ExitCode::from(2)
    })
}

fn cmd_sample(args: &[String]) -> ExitCode {
    let Some((path, vals)) = args.split_first() else {
        eprintln!("usage: kmx sample <file.kmx> <v0> [v1 ...]");
        return ExitCode::from(2);
    };
    let circuit = match load_circuit(path) {
        Ok(c) => c,
        Err(code) => return code,
    };
    let values: Vec<u128> = match vals.iter().map(|v| v.parse::<u128>()).collect() {
        Ok(v) => v,
        Err(_) => {
            eprintln!("register values must be non-negative integers");
            return ExitCode::from(2);
        }
    };

    let mut state = State::new(circuit.num_qubits, circuit.num_bits);
    for (i, &reg) in circuit.registers.keys().enumerate() {
        load_register(
            &mut state,
            &circuit,
            reg,
            values.get(i).copied().unwrap_or(0),
        );
    }
    // Deterministic measurement stream for sampling (seed 0).
    let mut measure = SplitMix64::new(0);
    run(&circuit, &mut state, &mut measure);

    let outs: Vec<String> = circuit
        .registers
        .keys()
        .map(|&reg| read_register(&state, &circuit, reg).to_string())
        .collect();
    println!("{}", outs.join(" "));
    ExitCode::SUCCESS
}

fn cmd_fuzz(args: &[String]) -> ExitCode {
    let mut path: Option<&str> = None;
    let mut shots: usize = 1;
    let mut seed: u64 = 0;
    let mut it = args.iter();
    while let Some(a) = it.next() {
        match a.as_str() {
            "--shots" => shots = it.next().and_then(|s| s.parse().ok()).unwrap_or(1),
            "--seed" => seed = it.next().and_then(|s| s.parse().ok()).unwrap_or(0),
            other => path = Some(other),
        }
    }
    let Some(path) = path else {
        eprintln!("usage: kmx fuzz <file.kmx> [--shots N] [--seed S] < cases");
        return ExitCode::from(2);
    };
    let circuit = match load_circuit(path) {
        Ok(c) => c,
        Err(code) => return code,
    };

    let mut input = String::new();
    if std::io::stdin().read_to_string(&mut input).is_err() {
        eprintln!("failed to read cases from stdin");
        return ExitCode::from(2);
    }
    let cases = match parse_cases(&input) {
        Ok(c) => c,
        Err(e) => {
            eprintln!("bad case line: {e}");
            return ExitCode::from(2);
        }
    };

    // A single shot with shots==1 uses a deterministic per-case stream so the
    // classical circuits reproduce example_fuzz exactly; >1 shot samples HMR.
    if shots <= 1 {
        for (ci, case) in cases.iter().enumerate() {
            let mut measure = SplitMix64::new(seed);
            if let Some(failure) = check_case(&circuit, case, &mut measure) {
                report_failure(ci, &case_str(case), &failure);
                return ExitCode::FAILURE;
            }
        }
        println!("pass ({} shots)", cases.len());
        return ExitCode::SUCCESS;
    }

    match fuzz(&circuit, &cases, shots, seed) {
        Ok(total) => {
            println!("pass ({total} shots)");
            ExitCode::SUCCESS
        }
        Err((ci, failure)) => {
            report_failure(ci, &case_str(&cases[ci]), &failure);
            ExitCode::FAILURE
        }
    }
}

fn report_failure(index: usize, case: &str, failure: &kickmix::FuzzFailure) {
    eprintln!("Test failed (case {index}): {case}");
    eprintln!("    {failure}");
}

fn case_str(case: &FuzzCase) -> String {
    let lhs: Vec<String> = case.inputs.iter().map(|v| v.to_string()).collect();
    let rhs: Vec<String> = case.outputs.iter().map(|v| v.to_string()).collect();
    format!("{} -> {}", lhs.join(" "), rhs.join(" "))
}

fn parse_cases(input: &str) -> Result<Vec<FuzzCase>, String> {
    let mut cases = Vec::new();
    for raw in input.lines() {
        let line = raw.trim();
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        let (lhs, rhs) = line
            .split_once("->")
            .ok_or_else(|| format!("{line:?}: missing `->`"))?;
        let inputs = parse_ints(lhs)?;
        let outputs = parse_ints(rhs)?;
        cases.push(FuzzCase { inputs, outputs });
    }
    Ok(cases)
}

fn parse_ints(s: &str) -> Result<Vec<u128>, String> {
    s.split_whitespace()
        .map(|t| {
            t.parse::<u128>()
                .map_err(|_| format!("{t:?}: not an integer"))
        })
        .collect()
}
