/**
 * @file        conf.c
 * @brief       A third library made only to be installed by the tests, with what 4.0.0 brings.
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

#include "conf.h"

/*
 * ****************************************************************************************************
 * Public function implementations
 * ****************************************************************************************************
*/

/*****************************************************************************************************/
/**
 * @brief The number of preemptible priorities, which zephyr.library.conf in installer.yml sets.
 *
 * @return CONFIG_NUM_PREEMPT_PRIORITIES: 20 from the library's Kconfig fragment, which Zephyr
 *         reads after prj.conf and its 12.
 */
int conf_answer(void)
{
    return CONFIG_NUM_PREEMPT_PRIORITIES;
}
