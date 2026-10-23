/**
 * @file        parts.c
 * @brief       A fourth library made only to be installed by the tests, with what 4.0.0 brings.
 * @version     1.0.0
 *
 * @author      Nima Askari (NimaLTD)
 * @email       nima.askari@gmail.com
 * @github      https://www.github.com/nimaltd
 * @linkedin    https://www.linkedin.com/in/nimaltd
 * @youtube     https://www.youtube.com/@nimaltd
 * @instagram   https://instagram.com/github.nimaltd
 *
 * @copyright   (c) 2026 Nima Askari (NimaLTD)
 *              SPDX-License-Identifier: Apache-2.0
 *              See LICENSE in the project root for the full license text.
 */

/*
 * ****************************************************************************************************
 * Includes
 * ****************************************************************************************************
*/

#include "parts.h"
#include "esp_timer.h"
#include "sdkconfig.h"

/*
 * ****************************************************************************************************
 * Build checks
 * ****************************************************************************************************
*/

/* esp_timer.h above is found only through esp32.library.requires, the REQUIRES lib-installer wrote. */

/* From esp32.library.cmake, the lines lib-installer wrote into the component's CMakeLists.txt. */
#ifndef PARTS_OWN
#error "PARTS_OWN, from parts' esp32.library.cmake, did not reach parts.c"
#endif

/*
 * ****************************************************************************************************
 * Public function implementations
 * ****************************************************************************************************
*/

/*****************************************************************************************************/
/**
 * @brief Two more than CONFIG_PARTS_BASE, which esp32.project.conf in installer.yml sets.
 *
 * @return 22: CONFIG_PARTS_BASE is 20 from the line lib-installer wrote into the project's
 *         sdkconfig.defaults, over the setting's default of 1.
 */
int parts_answer(void)
{
    return CONFIG_PARTS_BASE + 2;
}
