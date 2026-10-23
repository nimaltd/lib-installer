/**
 * @file        conf.h
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

#ifndef CONF_H
#define CONF_H

#ifdef __cplusplus
extern "C"
{
#endif

/*****************************************************************************************************/
/**
 * @brief The number of preemptible priorities, which zephyr.library.conf in installer.yml sets.
 */
int conf_answer(void);

#ifdef __cplusplus
}
#endif

#endif /* CONF_H */
