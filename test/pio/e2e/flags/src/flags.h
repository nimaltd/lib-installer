/**
 * @file        flags.h
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

#ifndef FLAGS_H
#define FLAGS_H

/*
 * ****************************************************************************************************
 * Build checks
 * ****************************************************************************************************
*/

/* From pio.project.build_flags, through build_flags in platformio.ini: every file of the build has
   to see it, the project's own code including this header as much as flags.c. */
#ifndef FLAGS_LEVEL
#error "FLAGS_LEVEL, from flags' pio.project.build_flags, did not reach the code including flags.h"
#endif

#ifdef __cplusplus
extern "C"
{
#endif

/*
 * ****************************************************************************************************
 * Public function prototypes
 * ****************************************************************************************************
*/

/*****************************************************************************************************/
/**
 * @brief The level build_flags in platformio.ini gives every file of the build.
 */
int flags_answer(void);

#ifdef __cplusplus
}
#endif

#endif /* FLAGS_H */
