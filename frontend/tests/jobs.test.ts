import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import JobCard from '../src/components/JobCard.vue'
import { job } from './fixtures'
import type { Job } from '../src/types/jobs'
const render = (changes: Partial<Job>) => mount(JobCard, { props: { job: job(changes) } })
describe('job presentation', () => {
  it('shows queued work with cancel and readable timestamps', () => {
    const wrapper = render({})
    expect(wrapper.text()).toContain('Queued')
    expect(wrapper.text()).toContain('Cancel')
    expect(wrapper.text()).not.toContain('Retry')
    expect(wrapper.text()).not.toContain('Invalid Date')
  })
  it('shows active percentage without inferring completion', () => {
    const wrapper = render({
      status: 'downloading',
      current_step: 'downloading',
      progress_percent: 100,
    })
    expect(wrapper.get('progress').attributes('value')).toBe('100')
    expect(wrapper.text()).toContain('Downloading')
    expect(wrapper.text()).not.toContain('Completed')
  })
  it.each([null, 0])('shows unknown/reset progress as indeterminate', (progress) => {
    const wrapper = render({
      status: 'processing',
      progress_percent: progress,
      current_step: 'validating',
    })
    expect(wrapper.get('progress').attributes('value')).toBeUndefined()
    expect(wrapper.text()).toContain('Validating')
    expect(wrapper.text()).not.toContain('0%')
  })
  it('shows cooperative cancellation without a terminal assumption', () => {
    const wrapper = render({ status: 'downloading', cancel_requested_at: '2026-10-03T00:00:01Z' })
    expect(wrapper.text()).toContain('Cancelling…')
    expect(wrapper.find('button').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('Cancelled')
  })
  it.each(['completed', 'cancelled', 'skipped_duplicate'] as const)(
    'hides cancel/retry on terminal %s',
    (status) => {
      const wrapper = render({ status })
      expect(wrapper.find('button').exists()).toBe(false)
    },
  )
  it('offers retry only while failed attempts remain and emits the job identity', async () => {
    const wrapper = render({
      status: 'failed',
      attempt_count: 1,
      error: { code: 'DOWNLOAD_FAILED', message: 'Download failed' },
    })
    expect(wrapper.text()).toContain('DOWNLOAD_FAILED')
    await wrapper.get('button').trigger('click')
    expect(wrapper.emitted('retry')?.[0]).toEqual([job().id])
    await wrapper.setProps({ job: job({ status: 'failed', attempt_count: 3 }) })
    expect(wrapper.find('button').exists()).toBe(false)
    expect(wrapper.text()).toContain('Attempt limit reached')
  })
})
