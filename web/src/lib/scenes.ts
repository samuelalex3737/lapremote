import type { SceneStep } from './protocol.ts'

/** One short line per scene step, for lists. */
export function describeStep(step: SceneStep, shortcutName: (id: string) => string): string {
  switch (step.type) {
    case 'volume.set':
      return `Volume ${String(step.level)}%`
    case 'brightness.set':
      return `Brightness ${String(step.level)}%`
    case 'launch.open':
      return `Open ${shortcutName(step.shortcutId)}`
    case 'media.play':
      return 'Play'
    case 'media.pause':
      return 'Pause'
    case 'wait':
      return `Wait ${String(step.ms / 1000)}s`
  }
}
