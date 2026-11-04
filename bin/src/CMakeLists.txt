cmake_minimum_required(VERSION 3.20)
project(kuhul_phase_runtime LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_library(kuhul_phase_runtime STATIC
  bindings.cpp
  chen.cpp
  operators.cpp
  pop.cpp
  sek.cpp
  vectors.cpp
  wo.cpp
  xcfe.cpp
  heuristic.cpp
  parser.cpp
  xpath_evaluator.cpp
  xul.cpp
  yax.cpp
)

target_include_directories(kuhul_phase_runtime PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})

add_executable(kuhul_phase_runtime_cli main.cpp)
target_link_libraries(kuhul_phase_runtime_cli PRIVATE kuhul_phase_runtime)
set_target_properties(kuhul_phase_runtime_cli PROPERTIES
  OUTPUT_NAME "kuhul_phase_runtime"
  RUNTIME_OUTPUT_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/..")
foreach(config DEBUG RELEASE RELWITHDEBINFO MINSIZEREL)
  set_target_properties(kuhul_phase_runtime_cli PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY_${config} "${CMAKE_CURRENT_SOURCE_DIR}/..")
endforeach()
target_compile_definitions(kuhul_phase_runtime_cli PRIVATE
  KUHUL_XPATH_EVALUATOR_PATH="${CMAKE_CURRENT_BINARY_DIR}/xpath_eval.py")
configure_file(xpath_eval.py "${CMAKE_CURRENT_BINARY_DIR}/xpath_eval.py" COPYONLY)
add_custom_target(kuhul_xpath_adapter ALL
  COMMAND ${CMAKE_COMMAND} -E make_directory "$<TARGET_FILE_DIR:kuhul_phase_runtime_cli>"
  COMMAND ${CMAKE_COMMAND} -E copy_if_different
    "${CMAKE_CURRENT_SOURCE_DIR}/xpath_eval.py"
    "$<TARGET_FILE_DIR:kuhul_phase_runtime_cli>/xpath_eval.py"
  DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/xpath_eval.py")
add_dependencies(kuhul_phase_runtime_cli kuhul_xpath_adapter)

find_package(Python3 COMPONENTS Interpreter REQUIRED)
include(CTest)
enable_testing()
add_test(NAME kuhul_xpath_conformance
  COMMAND ${Python3_EXECUTABLE}
    "${CMAKE_CURRENT_SOURCE_DIR}/../../tools/check_xpath_kbnf_conformance.py"
    --runtime-cli "$<TARGET_FILE:kuhul_phase_runtime_cli>")
add_test(NAME kuhul_feed_serializer_conformance
  COMMAND ${Python3_EXECUTABLE}
    "${CMAKE_CURRENT_SOURCE_DIR}/../../tools/check_kuhul_feed_serializer.py")

if(MSVC)
  target_compile_options(kuhul_phase_runtime PRIVATE /W4 /permissive-)
else()
  target_compile_options(kuhul_phase_runtime PRIVATE -Wall -Wextra -Wpedantic)
endif()

