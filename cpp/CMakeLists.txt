cmake_minimum_required(VERSION 3.16)
project(expense_tracker LANGUAGES CXX)

add_executable(expense_tracker main.cpp tracker.cpp)
target_compile_features(expense_tracker PRIVATE cxx_std_17)
set_target_properties(expense_tracker PROPERTIES CXX_EXTENSIONS OFF)

if(MSVC)
    target_compile_options(expense_tracker PRIVATE /W4 /permissive-)
else()
    target_compile_options(expense_tracker PRIVATE -Wall -Wextra -Wpedantic)
endif()
