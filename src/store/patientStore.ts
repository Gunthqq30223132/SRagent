import { create } from 'zustand'
import type { PatientData, ASAClass } from '@/types/medical'

interface PatientStore {
  patient: PatientData
  setWeight: (kg: number) => void
  setAge: (years: number) => void
  setHeight: (cm: number) => void
  setSex: (sex: 'male' | 'female') => void
  setASA: (cls: ASAClass) => void
  reset: () => void
}

const defaultPatient: PatientData = {
  weightKg: 60,
  ageYears: 40,
  heightCm: 165,
  sex: 'male',
}

export const usePatientStore = create<PatientStore>((set) => ({
  patient: defaultPatient,

  setWeight: (kg) => set((s) => ({ patient: { ...s.patient, weightKg: kg } })),
  setAge: (years) => set((s) => ({ patient: { ...s.patient, ageYears: years } })),
  setHeight: (cm) => set((s) => ({ patient: { ...s.patient, heightCm: cm } })),
  setSex: (sex) => set((s) => ({ patient: { ...s.patient, sex } })),
  setASA: (cls) => set((s) => ({ patient: { ...s.patient, asaScore: cls } })),
  reset: () => set({ patient: defaultPatient }),
}))
