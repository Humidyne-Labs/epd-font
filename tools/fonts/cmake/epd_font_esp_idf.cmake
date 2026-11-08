# ==============================================================================
# epd_font_esp_idf.cmake (v1.0.22)
# A 1-bit EPD font generator and asset pipeline for embedded displays
# Repository : https://github.com/Humidyne-Labs/epd-font
# Authors    : Humiditron (https://github.com/humiditron) & AI/LLM Development Partner
# License    : MIT License
# ==============================================================================

find_package(Python3 COMPONENTS Interpreter REQUIRED)

function(epd_font_generate_lvgl_target)
    set(options "")
    set(oneValueArgs TARGET_NAME SCHEME VAULT SRC_DIR OUT_DIR ASCII_DIR)
    set(multiValueArgs "")
    cmake_parse_arguments(EPD_FONT "${options}" "${oneValueArgs}" "${multiValueArgs}" ${ARGN})

    if(NOT EPD_FONT_TARGET_NAME)
        message(FATAL_ERROR "[epd-font] TARGET_NAME is required in epd_font_generate_lvgl_target()")
    endif()
    if(NOT EPD_FONT_SCHEME)
        message(FATAL_ERROR "[epd-font] SCHEME (.scheme.json path) is required in epd_font_generate_lvgl_target()")
    endif()
    if(NOT EPD_FONT_OUT_DIR)
        set(EPD_FONT_OUT_DIR "${CMAKE_CURRENT_BINARY_DIR}/generated_epd_fonts")
    endif()

    set(BUILDER_SCRIPT "${CMAKE_CURRENT_FUNCTION_LIST_DIR}/../tools/humid1_cmake_font_builder.py")
    if(NOT EXISTS "${BUILDER_SCRIPT}")
        set(BUILDER_SCRIPT "${CMAKE_CURRENT_FUNCTION_LIST_DIR}/../humid1_cmake_font_builder.py")
    endif()

    set(CMD_ARGS
        "${BUILDER_SCRIPT}"
        "--scheme" "${EPD_FONT_SCHEME}"
        "--out-dir" "${EPD_FONT_OUT_DIR}"
        "--list-sources"
    )
    if(EPD_FONT_VAULT)
        list(APPEND CMD_ARGS "--vault" "${EPD_FONT_VAULT}")
    elseif(EPD_FONT_SRC_DIR)
        list(APPEND CMD_ARGS "--src-dir" "${EPD_FONT_SRC_DIR}")
    endif()
    if(EPD_FONT_ASCII_DIR)
        list(APPEND CMD_ARGS "--ascii-dir" "${EPD_FONT_ASCII_DIR}")
    endif()

    execute_process(
        COMMAND "${Python3_EXECUTABLE}" ${CMD_ARGS}
        OUTPUT_VARIABLE EPD_FONT_GENERATED_SOURCES
        OUTPUT_STRIP_TRAILING_WHITESPACE
        RESULT_VARIABLE EPD_FONT_RESULT
    )
    if(NOT EPD_FONT_RESULT EQUAL 0)
        message(FATAL_ERROR "[epd-font] Font generation failed with exit code ${EPD_FONT_RESULT}")
    endif()

    add_library(${EPD_FONT_TARGET_NAME} STATIC ${EPD_FONT_GENERATED_SOURCES})
    target_include_directories(${EPD_FONT_TARGET_NAME} PUBLIC "${EPD_FONT_OUT_DIR}" "${EPD_FONT_OUT_DIR}/fonts")
    if(TARGET lvgl)
        target_link_libraries(${EPD_FONT_TARGET_NAME} PUBLIC lvgl)
    elseif(TARGET idf::lvgl)
        target_link_libraries(${EPD_FONT_TARGET_NAME} PUBLIC idf::lvgl)
    endif()
endfunction()
