# Minimal CMake project proving the C++ toolchain (gcc + cmake) works
# end-to-end on the dev workstation. This is a concrete, tested guarantee -
# not an assumption - that later native components (e.g. whisper.cpp
# integration in Phase 5) can actually be built here.
cmake_minimum_required(VERSION 3.16)
project(at_cpp_env_check CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_executable(at_cpp_env_check main.cpp)
