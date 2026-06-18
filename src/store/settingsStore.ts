import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface SettingsStore {
  theme: 'dark' | 'light'
  weightUnit: 'kg' | 'lb'
  disclaimerAccepted: boolean
  hospitalName: string
  setTheme: (t: 'dark' | 'light') => void
  setWeightUnit: (u: 'kg' | 'lb') => void
  acceptDisclaimer: () => void
  setHospitalName: (name: string) => void
}

export const useSettingsStore = create<SettingsStore>()(
  persist(
    (set) => ({
      theme: 'dark',
      weightUnit: 'kg',
      disclaimerAccepted: false,
      hospitalName: '',

      setTheme: (theme) => set({ theme }),
      setWeightUnit: (weightUnit) => set({ weightUnit }),
      acceptDisclaimer: () => set({ disclaimerAccepted: true }),
      setHospitalName: (hospitalName) => set({ hospitalName }),
    }),
    { name: 'anaesthesia-vn-settings' },
  ),
)
