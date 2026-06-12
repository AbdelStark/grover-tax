%builtins output pedersen range_check ecdsa bitwise ec_op keccak poseidon range_check96 add_mod mul_mod

from starkware.cairo.common.uint256 import Uint256, uint256_add

func main{
    output_ptr,
    pedersen_ptr,
    range_check_ptr,
    ecdsa_ptr,
    bitwise_ptr,
    ec_op_ptr,
    keccak_ptr,
    poseidon_ptr,
    range_check96_ptr,
    add_mod_ptr,
    mul_mod_ptr,
}() {
    alloc_locals;

    local iterations;
    %{ ids.iterations = program_input['iterations'] %}

    let start = Uint256(
        low=0x0123456789abcdef0123456789abcdef,
        high=0x000102030405060708090a0b0c0d0e0f,
    );
    let addend = Uint256(
        low=0x000000000000000000000000499602d2,
        high=0x00000000000000000000000000000000,
    );

    let (res) = repeat_iadd256(start, addend, iterations);

    return ();
}

func repeat_iadd256{range_check_ptr}(acc: Uint256, addend: Uint256, n: felt) -> (res: Uint256) {
    alloc_locals;

    if (n == 0) {
        return (res=acc);
    }

    let (next, carry) = uint256_add(acc, addend);

    return repeat_iadd256(next, addend, n - 1);
}
