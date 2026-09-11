// Proves the C++17 toolchain builds and runs on this workstation.
// Exit code 0 + expected stdout == the toolchain is verified, not assumed.
#include <iostream>

int main() {
    std::cout << "AT_CPP_ENV_CHECK_OK" << std::endl;
    return 0;
}
