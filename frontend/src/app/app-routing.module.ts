import { NgModule } from '@angular/core';
import { RouterModule, Routes } from '@angular/router';
import { PageprincipaleComponent } from './pageprincipale/pageprincipale.component';
import { ContactComponent } from './contact/contact.component';

const routes: Routes = [
  {path: '', redirectTo: '/home', pathMatch: 'full'}, 
  {path:'home', component: PageprincipaleComponent},
  {path :'contact',component: ContactComponent},
];

@NgModule({
  imports: [RouterModule.forRoot(routes)],
  exports: [RouterModule]
})
export class AppRoutingModule { }
